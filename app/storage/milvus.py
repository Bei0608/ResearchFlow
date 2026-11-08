import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_milvus import Milvus

from app.rag.embeddings import get_embedding_model

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_MILVUS_URI = "http://localhost:19530"
DEFAULT_COLLECTION_NAME = "researchflow_chunks_v1"


def get_milvus_uri() -> str:
    """读取Milvus连接地址。"""
    load_dotenv(
        dotenv_path=ENV_FILE,
        override=False,
    )

    return os.getenv(
        "MILVUS_URI",
        DEFAULT_MILVUS_URI,
    )


def get_milvus_collection_name() -> str:
    """读取Milvus集合名称。"""
    load_dotenv(
        dotenv_path=ENV_FILE,
        override=False,
    )

    return os.getenv(
        "MILVUS_COLLECTION",
        DEFAULT_COLLECTION_NAME,
    )


@lru_cache(maxsize=1)
def get_milvus_vector_store() -> Milvus:
    """创建并缓存ResearchFlow使用的Milvus向量存储。"""
    return Milvus(
        embedding_function=get_embedding_model(),
        collection_name=get_milvus_collection_name(),
        collection_description=("ResearchFlow论文文本块向量集合"),
        connection_args={
            "uri": get_milvus_uri(),
        },
        consistency_level="Session",
        index_params={
            "index_type": "AUTOINDEX",
            "metric_type": "COSINE",
            "params": {},
        },
        search_params={
            "metric_type": "COSINE",
            "params": {},
        },
        drop_old=False,
        auto_id=False,
        primary_field="pk",
        text_field="text",
        vector_field="vector",
        enable_dynamic_field=True,
    )
