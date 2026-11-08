from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.store.base import BaseStore

from app.api.dependencies import get_current_user, provide_memory_store
from app.api.schemas import (
    MemoryItem,
    MemoryListResponse,
    MemoryUpdateRequest,
)
from app.tools.memory_tools import (
    build_memory_namespace,
    normalize_memory_fields,
)
from app.security import UserRecord


router = APIRouter(
    prefix="/users/me/memories",
    tags=["memories"],
)


@router.get("", response_model=MemoryListResponse)
def list_memories(
    user: Annotated[UserRecord, Depends(get_current_user)],
    store: BaseStore = Depends(provide_memory_store),
) -> MemoryListResponse:
    """列出指定用户的长期记忆。"""
    namespace = build_memory_namespace(user.user_id)
    items = store.search(namespace, limit=50)

    return MemoryListResponse(
        user_id=user.user_id,
        memories=[
            MemoryItem(
                memory_id=item.key,
                category=str(
                    item.value.get("category", "unknown")
                ),
                content=str(item.value.get("content", "")),
            )
            for item in items
        ],
    )


@router.put(
    "/{memory_id}",
    response_model=MemoryItem,
)
def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    user: Annotated[UserRecord, Depends(get_current_user)],
    store: BaseStore = Depends(provide_memory_store),
) -> MemoryItem:
    """更新指定用户的一条长期记忆。"""
    namespace = build_memory_namespace(user.user_id)
    existing = store.get(namespace, memory_id)

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="长期记忆不存在",
        )

    category, content = normalize_memory_fields(
        request.category,
        request.content,
    )
    store.put(
        namespace,
        memory_id,
        {
            "category": category,
            "content": content,
        },
    )

    return MemoryItem(
        memory_id=memory_id,
        category=category,
        content=content,
    )


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_memory(
    memory_id: str,
    user: Annotated[UserRecord, Depends(get_current_user)],
    store: BaseStore = Depends(provide_memory_store),
) -> None:
    """删除指定用户的一条长期记忆。"""
    namespace = build_memory_namespace(user.user_id)
    existing = store.get(namespace, memory_id)

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="长期记忆不存在",
        )

    store.delete(namespace, memory_id)
