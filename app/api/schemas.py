from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    """API模型的共同严格配置。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ChatRequest(APIModel):
    question: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )


class ChatResponse(APIModel):
    answer: str
    user_id: str
    thread_id: str


class ResearchRequest(APIModel):
    question: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    top_k: int = Field(default=5, ge=1, le=10)
    min_score: float = Field(default=0.45, ge=0, le=1)


class ResearchResponse(APIModel):
    answer: str
    user_id: str
    thread_id: str
    route: Literal["answer", "insufficient", "error"]
    evidence_count: int = Field(ge=0)
    citations: list[str]
    executed_nodes: list[str]
    judge_reason: str | None = None


class MemoryItem(APIModel):
    memory_id: str
    category: str
    content: str


class MemoryListResponse(APIModel):
    user_id: str
    memories: list[MemoryItem]


class MemoryUpdateRequest(APIModel):
    category: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=4000)


class HealthResponse(APIModel):
    status: Literal["ok", "degraded"]
    service: str = "researchflow"


class ReadinessResponse(HealthResponse):
    postgres: bool
    milvus: bool
    redis: bool


class RegisterRequest(APIModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    password: str = Field(min_length=8, max_length=128)


class UserResponse(APIModel):
    user_id: str
    username: str
    is_active: bool


class TokenResponse(APIModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    refresh_token: str
    refresh_expires_in: int = Field(gt=0)


class MCPTokenResponse(APIModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    scope: str
    resource: str


class RefreshTokenRequest(APIModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class LogoutResponse(APIModel):
    revoked: bool


class ChangePasswordRequest(APIModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class ChangePasswordResponse(APIModel):
    changed: bool
    revoked_refresh_sessions: int = Field(ge=0)


class AuditEventResponse(APIModel):
    event_id: str
    event_type: str
    resource: str
    outcome: str
    request_id: str | None
    metadata: dict
    created_at: datetime


class AuditEventListResponse(APIModel):
    user_id: str
    events: list[AuditEventResponse]
