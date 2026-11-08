from functools import lru_cache

from langgraph.store.postgres import PostgresStore

from app.memory.checkpointer import get_postgres_pool


@lru_cache(maxsize=1)
def get_postgres_store() -> PostgresStore:
    """创建并初始化长期记忆使用的PostgreSQL Store。"""
    store = PostgresStore(
        conn=get_postgres_pool(),
    )

    # 创建或升级PostgresStore需要的数据表。
    # setup()可以安全地重复调用。
    store.setup()

    return store
