import json
import re
from typing import Any


class SensitiveConfigError(ValueError):
    """Raised when a version snapshot contains raw credentials."""


_SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "token",
}


def _normalize_key(key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    return normalized


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalize_key(key)
    return (
        normalized in _SENSITIVE_KEYS
        or normalized.endswith("_api_key")
        or normalized.endswith("_password")
        or normalized.endswith("_secret")
        or normalized.endswith("_token")
    )


def _find_sensitive_path(value: Any, path: str = "config") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_sensitive_key(key_text):
                return child_path
            found = _find_sensitive_path(child, child_path)
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_sensitive_path(child, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def prepare_config_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    """Reject credentials and return a detached JSON-compatible snapshot."""
    sensitive_path = _find_sensitive_path(config)
    if sensitive_path is not None:
        raise SensitiveConfigError(
            f"配置快照不得包含敏感字段：{sensitive_path}；请保存密钥引用"
        )
    try:
        serialized = json.dumps(config, ensure_ascii=False, sort_keys=True)
        snapshot = json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise ValueError("配置快照必须是可序列化的JSON对象") from exc
    if not isinstance(snapshot, dict):
        raise ValueError("配置快照必须是JSON对象")
    return snapshot
