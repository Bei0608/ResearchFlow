from uuid import uuid4

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.agent.research_agent import run_research_agent
from app.api.dependencies import (
    get_current_user,
    provide_identity_repository,
    require_thread_owner,
)
from app.api.schemas import ChatRequest, ChatResponse
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event


router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.post("", response_model=ChatResponse)
def chat(
    http_request: Request,
    request: ChatRequest,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> ChatResponse:
    """运行具备工具与长期记忆能力的Research Agent。"""
    thread_id = request.thread_id or uuid4().hex
    require_thread_owner(thread_id, user, repository)
    result = run_research_agent(
        question=request.question,
        user_id=user.user_id,
        thread_id=thread_id,
    )
    content = result["messages"][-1].content
    record_audit_event(
        repository,
        http_request,
        user_id=user.user_id,
        event_type="agent.completed",
        resource=f"thread:{thread_id}",
    )

    return ChatResponse(
        answer=(
            content
            if isinstance(content, str)
            else str(content)
        ),
        user_id=user.user_id,
        thread_id=thread_id,
    )
