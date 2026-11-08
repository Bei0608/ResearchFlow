import json
from hashlib import sha256
from uuid import uuid4

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.store.base import BaseStore

from app.models import ResearchContext


def build_memory_namespace(
    user_id: str,
) -> tuple[str, ...]:
    """为用户生成相互隔离的长期记忆命名空间。"""
    normalized_user_id = user_id.strip()

    if not normalized_user_id:
        raise ValueError("user_id不能为空")

    user_hash = sha256(normalized_user_id.encode("utf-8")).hexdigest()

    return (
        "researchflow",
        "users",
        user_hash,
        "memories",
    )


def get_memory_runtime(
    runtime: ToolRuntime[ResearchContext],
) -> tuple[str, BaseStore]:
    """从工具运行环境中取得当前用户和Store。"""
    if runtime.context is None:
        raise RuntimeError("缺少Agent运行上下文")

    if runtime.store is None:
        raise RuntimeError("Agent没有配置长期记忆Store")

    user_id = runtime.context.user_id.strip()

    if not user_id:
        raise RuntimeError("Agent运行上下文中的user_id为空")

    return user_id, runtime.store


def normalize_memory_fields(
    category: str,
    content: str,
) -> tuple[str, str]:
    """清理并验证长期记忆的类别和内容。"""
    normalized_category = category.strip().lower()
    normalized_content = content.strip()

    if not normalized_category:
        raise ValueError("记忆类别不能为空")

    if not normalized_content:
        raise ValueError("记忆内容不能为空")

    return (
        normalized_category,
        normalized_content,
    )


@tool
def save_user_memory(
    category: str,
    content: str,
    runtime: ToolRuntime[ResearchContext],
) -> str:
    """
    保存当前用户明确要求长期记住的信息。

    只有当用户明确要求记住、保存或以后参考某项信息时才使用。
    如果用户是在修改已有记忆，应先读取记忆并使用update_user_memory。
    category是记忆类别，例如response_preference、research_interest或goal。
    content是经过简洁整理后需要长期保存的内容。
    """
    user_id, store = get_memory_runtime(runtime)

    try:
        (
            normalized_category,
            normalized_content,
        ) = normalize_memory_fields(
            category=category,
            content=content,
        )
    except ValueError as exception:
        return f"保存失败：{exception}。"

    namespace = build_memory_namespace(user_id)

    duplicate_items = store.search(
        namespace,
        filter={
            "category": normalized_category,
            "content": normalized_content,
        },
        limit=1,
    )

    if duplicate_items:
        existing_item = duplicate_items[0]

        return json.dumps(
            {
                "status": "already_exists",
                "memory_id": existing_item.key,
                "category": normalized_category,
                "content": normalized_content,
            },
            ensure_ascii=False,
        )

    memory_id = uuid4().hex

    store.put(
        namespace=namespace,
        key=memory_id,
        value={
            "category": normalized_category,
            "content": normalized_content,
        },
    )

    return json.dumps(
        {
            "status": "saved",
            "memory_id": memory_id,
            "category": normalized_category,
            "content": normalized_content,
        },
        ensure_ascii=False,
    )


@tool
def list_user_memories(
    runtime: ToolRuntime[ResearchContext],
) -> str:
    """
    读取当前用户已经保存的长期记忆。

    当用户询问过去保存的偏好、研究兴趣、目标，或需要修改、删除某条记忆时使用。
    """
    user_id, store = get_memory_runtime(runtime)
    namespace = build_memory_namespace(user_id)

    items = store.search(
        namespace,
        limit=50,
    )

    if not items:
        return "当前用户还没有保存任何长期记忆。"

    memories = [
        {
            "memory_id": item.key,
            "category": item.value.get(
                "category",
                "unknown",
            ),
            "content": item.value.get(
                "content",
                "",
            ),
        }
        for item in items
    ]

    return json.dumps(
        memories,
        ensure_ascii=False,
        indent=2,
    )


@tool
def update_user_memory(
    memory_id: str,
    category: str,
    content: str,
    runtime: ToolRuntime[ResearchContext],
) -> str:
    """
    更新当前用户已经存在的一条长期记忆。

    当用户明确要求修改、替换或纠正已有记忆时使用。
    更新前应先通过list_user_memories取得准确的memory_id。
    category和content是更新后的完整类别与内容。
    """
    user_id, store = get_memory_runtime(runtime)

    normalized_memory_id = memory_id.strip()

    if not normalized_memory_id:
        return "更新失败：memory_id不能为空。"

    try:
        (
            normalized_category,
            normalized_content,
        ) = normalize_memory_fields(
            category=category,
            content=content,
        )
    except ValueError as exception:
        return f"更新失败：{exception}。"

    namespace = build_memory_namespace(user_id)

    existing_item = store.get(
        namespace=namespace,
        key=normalized_memory_id,
    )

    if existing_item is None:
        return json.dumps(
            {
                "status": "not_found",
                "memory_id": normalized_memory_id,
            },
            ensure_ascii=False,
        )

    store.put(
        namespace=namespace,
        key=normalized_memory_id,
        value={
            "category": normalized_category,
            "content": normalized_content,
        },
    )

    return json.dumps(
        {
            "status": "updated",
            "memory_id": normalized_memory_id,
            "category": normalized_category,
            "content": normalized_content,
        },
        ensure_ascii=False,
    )


@tool
def delete_user_memory(
    memory_id: str,
    runtime: ToolRuntime[ResearchContext],
) -> str:
    """
    删除当前用户指定的长期记忆。

    用户要求遗忘某项长期信息时使用。
    删除前应先通过list_user_memories取得准确的memory_id。
    """
    user_id, store = get_memory_runtime(runtime)

    normalized_memory_id = memory_id.strip()

    if not normalized_memory_id:
        return "删除失败：memory_id不能为空。"

    namespace = build_memory_namespace(user_id)

    existing_item = store.get(
        namespace=namespace,
        key=normalized_memory_id,
    )

    if existing_item is None:
        return json.dumps(
            {
                "status": "not_found",
                "memory_id": normalized_memory_id,
            },
            ensure_ascii=False,
        )

    store.delete(
        namespace=namespace,
        key=normalized_memory_id,
    )

    return json.dumps(
        {
            "status": "deleted",
            "memory_id": normalized_memory_id,
        },
        ensure_ascii=False,
    )


MEMORY_TOOLS = [
    save_user_memory,
    list_user_memories,
    delete_user_memory,
    update_user_memory,
]


__all__ = [
    "MEMORY_TOOLS",
    "build_memory_namespace",
    "delete_user_memory",
    "list_user_memories",
    "normalize_memory_fields",
    "save_user_memory",
    "update_user_memory",
]
