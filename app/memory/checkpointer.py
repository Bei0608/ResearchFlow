import atexit
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def get_postgres_uri() -> str:
    """读取PostgreSQL连接地址。"""
    load_dotenv(
        dotenv_path=ENV_FILE,
        override=False,
    )

    postgres_uri = os.getenv("POSTGRES_URI")

    if not postgres_uri:
        raise RuntimeError(
            f"缺少POSTGRES_URI，请检查：{ENV_FILE}"
        )

    return postgres_uri


@lru_cache(maxsize=1)
def get_postgres_pool() -> ConnectionPool:
    """创建并缓存Agent状态使用的PostgreSQL连接池。"""
    pool = ConnectionPool(
        conninfo=get_postgres_uri(),
        min_size=1,
        max_size=5,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=True,
        name="researchflow-checkpoint-pool",
    )

    pool.wait(timeout=10)
    atexit.register(pool.close)

    return pool


@lru_cache(maxsize=1)
def get_postgres_checkpointer() -> PostgresSaver:
    """创建并初始化PostgreSQL持久化Checkpointer。"""
    checkpointer = PostgresSaver(
        conn=get_postgres_pool(),
    )

    # setup()会创建或升级LangGraph所需表结构，可重复执行。
    checkpointer.setup()

    return checkpointer
