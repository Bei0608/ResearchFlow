from collections.abc import Iterator
from uuid import uuid4

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.dependencies import (
    get_current_user,
    provide_identity_repository,
    require_thread_owner,
)
from app.api.schemas import (
    ResearchRequest,
    ResearchResponse,
)
from app.workflows import (
    run_research_workflow,
    stream_research_workflow,
)
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event


router = APIRouter(
    prefix="/research",
    tags=["research"],
)


@router.post("", response_model=ResearchResponse)
def research(
    http_request: Request,
    request: ResearchRequest,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> ResearchResponse:
    """运行路径固定、可审计的LangGraph论文研究流程。"""
    thread_id = request.thread_id or uuid4().hex
    require_thread_owner(thread_id, user, repository)
    result = run_research_workflow(
        question=request.question,
        thread_id=thread_id,
        top_k=request.top_k,
        min_score=request.min_score,
    )
    record_audit_event(
        repository,
        http_request,
        user_id=user.user_id,
        event_type="research.completed",
        resource=f"thread:{thread_id}",
        outcome=result["route"],
        metadata={
            "evidence_count": len(result["evidence"]),
        },
    )

    return ResearchResponse(
        answer=result["answer"],
        user_id=user.user_id,
        thread_id=thread_id,
        route=result["route"],
        evidence_count=len(result["evidence"]),
        citations=result["citations"],
        executed_nodes=result["executed_nodes"],
        judge_reason=result.get("judge_reason"),
    )


@router.post(
    "/stream",
    response_class=EventSourceResponse,
    response_model=None,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "LangGraph节点进度与最终答案事件",
        }
    },
)
def research_stream(
    http_request: Request,
    request: ResearchRequest,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> Iterator[ServerSentEvent]:
    """以SSE实时返回LangGraph节点进度和最终答案。"""
    thread_id = request.thread_id or uuid4().hex
    require_thread_owner(thread_id, user, repository)

    def event_generator():
        try:
            yield ServerSentEvent(
                event="started",
                data={
                    "thread_id": thread_id,
                    "user_id": user.user_id,
                },
            )
            for event in stream_research_workflow(
                question=request.question,
                thread_id=thread_id,
                top_k=request.top_k,
                min_score=request.min_score,
            ):
                event_name = str(event["event"])
                if event_name == "completed":
                    record_audit_event(
                        repository,
                        http_request,
                        user_id=user.user_id,
                        event_type="research.stream_completed",
                        resource=f"thread:{thread_id}",
                        outcome=str(event.get("route", "completed")),
                        metadata={
                            "evidence_count": event.get(
                                "evidence_count",
                                0,
                            )
                        },
                    )
                yield ServerSentEvent(
                    event=event_name,
                    data={
                        "thread_id": thread_id,
                        **event,
                    },
                )
        except GeneratorExit:
            raise
        except Exception as exception:
            yield ServerSentEvent(
                event="error",
                data={
                    "thread_id": thread_id,
                    "error": type(exception).__name__,
                    "message": "研究流程执行失败",
                },
            )

    return event_generator()
