import os
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from time import time
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.observability.metrics import RATE_LIMIT_BACKEND_ERRORS


@dataclass(frozen=True)
class RateLimitSettings:
    """单进程固定窗口限流配置。"""

    requests: int = 60
    window_seconds: int = 60

    def __post_init__(self) -> None:
        if self.requests <= 0 or self.window_seconds <= 0:
            raise ValueError("限流请求数和窗口必须大于0")


def get_rate_limit_settings() -> RateLimitSettings:
    return RateLimitSettings(
        requests=int(os.getenv("RATE_LIMIT_REQUESTS", "60")),
        window_seconds=int(
            os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")
        ),
    )


class FixedWindowRateLimiter:
    """线程安全的内存固定窗口限流器。"""

    def __init__(self, settings: RateLimitSettings) -> None:
        self.settings = settings
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        """返回是否允许、剩余额度和重试秒数。"""
        now = monotonic()
        with self._lock:
            started_at, count = self._windows.get(
                key,
                (now, 0),
            )
            elapsed = now - started_at
            if elapsed >= self.settings.window_seconds:
                started_at, count = now, 0

            if count >= self.settings.requests:
                retry_after = max(
                    1,
                    int(
                        self.settings.window_seconds
                        - elapsed
                    )
                    + 1,
                )
                return False, 0, retry_after

            count += 1
            self._windows[key] = (started_at, count)
            remaining = self.settings.requests - count
            return True, remaining, 0


class RateLimiter(Protocol):
    def check(self, key: str) -> tuple[bool, int, int]: ...


REDIS_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class RedisRateLimiter:
    """跨进程共享的Redis原子固定窗口限流器。"""

    def __init__(
        self,
        client: Redis,
        settings: RateLimitSettings,
        fallback: RateLimiter | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.fallback = fallback or FixedWindowRateLimiter(settings)
        self._script = client.register_script(
            REDIS_FIXED_WINDOW_SCRIPT
        )

    def check(self, key: str) -> tuple[bool, int, int]:
        window = int(time()) // self.settings.window_seconds
        redis_key = f"researchflow:rate:{key}:{window}"
        try:
            current, ttl = self._script(
                keys=[redis_key],
                args=[self.settings.window_seconds],
            )
            count = int(current)
            retry_after = max(1, int(ttl))
            remaining = max(0, self.settings.requests - count)
            return (
                count <= self.settings.requests,
                remaining,
                0 if count <= self.settings.requests else retry_after,
            )
        except RedisError:
            RATE_LIMIT_BACKEND_ERRORS.inc()
            return self.fallback.check(key)


def build_rate_limiter(
    settings: RateLimitSettings | None = None,
) -> RateLimiter:
    resolved = settings or get_rate_limit_settings()
    redis_uri = os.getenv("REDIS_URI", "").strip()
    fallback = FixedWindowRateLimiter(resolved)
    if not redis_uri:
        return fallback
    client = Redis.from_url(
        redis_uri,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    return RedisRateLimiter(client, resolved, fallback)
