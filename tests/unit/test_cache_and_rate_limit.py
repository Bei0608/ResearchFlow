from redis.exceptions import RedisError

from app.api.rate_limit import (
    FixedWindowRateLimiter,
    RateLimitSettings,
    RedisRateLimiter,
)
from app.cache.redis_cache import RetrievalCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str | int] = {}
        self.counts: dict[str, int] = {}
        self.fail_script = False

    def get(self, key: str):
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        assert ttl > 0
        self.values[key] = value

    def incr(self, key: str) -> int:
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    def register_script(self, script: str):
        assert "INCR" in script

        def call(*, keys: list[str], args: list[int]):
            if self.fail_script:
                raise RedisError("redis unavailable")
            key = keys[0]
            self.counts[key] = self.counts.get(key, 0) + 1
            return [self.counts[key], args[0]]

        return call


def test_retrieval_cache_round_trip_and_version_bump() -> None:
    client = FakeRedis()
    cache = RetrievalCache(client, ttl_seconds=60)
    identity = {
        "query": "RT-2动作",
        "top_k": 5,
        "strategy": "mmr",
        "collection": "papers",
    }
    value = [{"chunk_id": "chunk-1"}]

    assert cache.get(**identity) is None
    cache.set(value, **identity)
    assert cache.get(**identity) == value

    cache.bump_index_version()
    assert cache.get(**identity) is None


def test_redis_rate_limiter_is_shared_and_atomic() -> None:
    client = FakeRedis()
    limiter = RedisRateLimiter(
        client,
        RateLimitSettings(requests=2, window_seconds=60),
    )

    assert limiter.check("client")[:2] == (True, 1)
    assert limiter.check("client")[:2] == (True, 0)
    allowed, remaining, retry_after = limiter.check("client")
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_redis_rate_limiter_falls_back_when_backend_fails() -> None:
    client = FakeRedis()
    client.fail_script = True
    fallback = FixedWindowRateLimiter(
        RateLimitSettings(requests=1, window_seconds=60)
    )
    limiter = RedisRateLimiter(
        client,
        RateLimitSettings(requests=1, window_seconds=60),
        fallback=fallback,
    )

    assert limiter.check("client")[0] is True
    assert limiter.check("client")[0] is False
