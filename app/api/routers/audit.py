from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_current_user,
    provide_identity_repository,
)
from app.api.schemas import (
    AuditEventListResponse,
    AuditEventResponse,
)
from app.security import IdentityRepository, UserRecord


router = APIRouter(prefix="/users/me/audit-events", tags=["audit"])


@router.get("", response_model=AuditEventListResponse)
def list_my_audit_events(
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> AuditEventListResponse:
    """只返回当前认证用户自己的安全与业务审计事件。"""
    events = repository.list_audit_events(user.user_id, limit)
    return AuditEventListResponse(
        user_id=user.user_id,
        events=[
            AuditEventResponse(
                event_id=event.event_id,
                event_type=event.event_type,
                resource=event.resource,
                outcome=event.outcome,
                request_id=event.request_id,
                metadata=event.metadata,
                created_at=event.created_at,
            )
            for event in events
        ],
    )
