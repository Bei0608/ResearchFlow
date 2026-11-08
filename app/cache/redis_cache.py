import hashlib
import json
import logging
import os
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.observability.metrics import RETRIEVAL_CACHE_OPERATIONS


logger = logging.getLogger("researchflow.cache")
INDEX_VERSION_KEY = "researchflow:index:version"


class RetrievalCache:
    """Redis cache-aside storage for serializable retrieval results."""

    def __init__(
        self,
        client: Redis,
        ttl_seconds: int = 300,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("缓存TTL必须大于0")
        self.client = client
        self.ttl_seconds = ttl_seconds

    def _key(
        self,
        *,
        query: str,
        top_k: int,
        strategy: str,
        collection: str,
    ) -> str:
        version = self.client.get(INDEX_VERSION_KEY) or "0"
        payload = json.dumps(
            {
                "query": query.strip().casefold(),
                "top_k": top_k,
                "strategy": strategy,
                "collection": collection,
                "version": str(version),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"researchflow:retrieval:{digest}"

    def get(self, **identity: Any) -> list[dict[str, Any]] | None:
        try:
            raw = self.client.get(self._key(**identity))
            if raw is None:
                RETRIEVAL_CACHE_OPERATIONS.labels(outcome="miss").inc()
                return None
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("缓存内容不是列表")
            RETRIEVAL_CACHE_OPERATIONS.labels(outcome="hit").inc()
            return data
        except (RedisError, ValueError, TypeError, json.JSONDecodeError):
            RETRIEVAL_CACHE_OPERATIONS.labels(outcome="error").inc()
            logger.warning("读取检索缓存失败，降级为实时检索", exc_info=True)
            return None

    def set(self, value: list[dict[str, Any]], **identity: Any) -> None:
        try:
            self.client.setex(
                self._key(**identity),
                self.ttl_seconds,
                json.dumps(value, ensure_ascii=False),
            )
            RETRIEVAL_CACHE_OPERATIONS.labels(outcome="write").inc()
        except (RedisError, TypeError, ValueError):
            RETRIEVAL_CACHE_OPERATIONS.labels(outcome="error").inc()
            logger.warning("写入检索缓存失败", exc_info=True)

    def bump_index_version(self) -> None:
        """索引变化后令旧缓存键自然失效。"""
        try:
            self.client.incr(INDEX_VERSION_KEY)
        except RedisError:
            logger.warning("更新检索缓存版本失败", exc_info=True)


@lru_cache(maxsize=1)
def get_retrieval_cache() -> RetrievalCache | None:
    enabled = os.getenv(
        "RETRIEVAL_CACHE_ENABLED",
        "true",
    ).lower() in {"1", "true", "yes"}
    redis_uri = os.getenv("REDIS_URI", "").strip()
    if not enabled or not redis_uri:
        return None
    client = Redis.from_url(
        redis_uri,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    return RetrievalCache(
        client,
        ttl_seconds=int(
            os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "300")
        ),
    )
