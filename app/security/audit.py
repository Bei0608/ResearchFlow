import logging
from typing import Any

from fastapi import Request

from app.security.repository import IdentityRepository


logger = logging.getLogger("researchflow.audit")


def record_audit_event(
    repository: IdentityRepository,
    request: Request,
    *,
    user_id: str | None,
    event_type: str,
    resource: str,
    outcome: str = "success",
    metadata: dict[str, Any] | None = None,
) -> None:
    """尽力写审计记录，不让审计后端故障破坏业务响应。"""
    try:
        repository.record_audit_event(
            user_id=user_id,
            event_type=event_type,
            resource=resource,
            outcome=outcome,
            request_id=getattr(request.state, "request_id", None),
            metadata=metadata,
        )
    except Exception:
        logger.exception("写入审计事件失败 event=%s", event_type)
