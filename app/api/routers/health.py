import os

from dotenv import load_dotenv
from fastapi import APIRouter
from pymilvus import MilvusClient
from redis import Redis

from app.api.schemas import (
    HealthResponse,
    ReadinessResponse,
)
from app.memory import get_postgres_store
from app.memory.checkpointer import ENV_FILE
from app.storage.milvus import get_milvus_uri


router = APIRouter(
    prefix="/health",
    tags=["health"],
)


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """确认HTTP进程仍能处理请求。"""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    """检查PostgreSQL、Milvus和Redis依赖是否可访问。"""
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    postgres_ready = False
    milvus_ready = False
    redis_ready = False

    try:
        get_postgres_store().search(
            ("researchflow", "health"),
            limit=1,
        )
        postgres_ready = True
    except Exception:
        postgres_ready = False

    try:
        client = MilvusClient(uri=get_milvus_uri())
        client.list_collections()
        client.close()
        milvus_ready = True
    except Exception:
        milvus_ready = False

    try:
        redis_uri = os.getenv("REDIS_URI", "")
        if redis_uri:
            client = Redis.from_url(
                redis_uri,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            redis_ready = bool(client.ping())
            client.close()
    except Exception:
        redis_ready = False

    status_value = (
        "ok"
        if postgres_ready and milvus_ready and redis_ready
        else "degraded"
    )

    return ReadinessResponse(
        status=status_value,
        postgres=postgres_ready,
        milvus=milvus_ready,
        redis=redis_ready,
    )
