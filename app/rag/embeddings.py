import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

EMBEDDING_MODEL = "openai:qwen3.7-text-embedding"
EMBEDDING_DIMENSIONS = 1024
EMBEDDING_BATCH_SIZE = 20
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2


def get_required_environment_variable(name: str) -> str:
    """读取必需环境变量，缺失时给出明确错误。"""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量{name}，请检查：{ENV_FILE}"
        )

    return value


@lru_cache(maxsize=1)
def get_embedding_model() -> Embeddings:
    """创建并缓存千问Embedding模型实例。"""
    load_dotenv(
        dotenv_path=ENV_FILE,
        override=False,
    )

    api_key = get_required_environment_variable(
        "QWEN_API_KEY"
    )
    base_url = get_required_environment_variable(
        "QWEN_BASE_URL"
    )

    return init_embeddings(
        model=EMBEDDING_MODEL,
        api_key=api_key,
        base_url=base_url,
        dimensions=EMBEDDING_DIMENSIONS,
        chunk_size=EMBEDDING_BATCH_SIZE,
        check_embedding_ctx_length=False,
        timeout=float(
            os.getenv(
                "EMBEDDING_TIMEOUT_SECONDS",
                str(DEFAULT_TIMEOUT_SECONDS),
            )
        ),
        max_retries=int(
            os.getenv(
                "EMBEDDING_MAX_RETRIES",
                str(DEFAULT_MAX_RETRIES),
            )
        ),
    )
