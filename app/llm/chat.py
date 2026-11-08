import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_CHAT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2


def get_required_environment_variable(name: str) -> str:
    """读取必需环境变量。"""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"缺少环境变量{name}，请检查：{ENV_FILE}")

    return value


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """创建并缓存回答阶段使用的聊天模型。"""
    load_dotenv(
        dotenv_path=ENV_FILE,
        override=False,
    )

    return ChatOpenAI(
        model=os.getenv(
            "DEEPSEEK_CHAT_MODEL",
            DEFAULT_CHAT_MODEL,
        ),
        api_key=get_required_environment_variable("DEEPSEEK_API_KEY"),
        base_url=get_required_environment_variable("DEEPSEEK_BASE_URL"),
        temperature=0,
        timeout=float(
            os.getenv(
                "LLM_TIMEOUT_SECONDS",
                str(DEFAULT_TIMEOUT_SECONDS),
            )
        ),
        max_retries=int(
            os.getenv(
                "LLM_MAX_RETRIES",
                str(DEFAULT_MAX_RETRIES),
            )
        ),
    )
