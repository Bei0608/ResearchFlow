from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.api.schemas import APIModel


class WorkspaceResponse(APIModel):
    workspace_id: str
    name: str
    owner_id: str
    is_personal: bool
    role: Literal["owner", "reviewer"]
    created_at: datetime


class WorkspaceListResponse(APIModel):
    workspaces: list[WorkspaceResponse]


class ReviewerAddRequest(APIModel):
    username: str = Field(min_length=1, max_length=64)


class ApplicationCreateRequest(APIModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1000)
    target_type: Literal["internal", "api", "mcp"] = "internal"


class ApplicationResponse(APIModel):
    application_id: str
    workspace_id: str
    name: str
    description: str
    target_type: Literal["internal", "api", "mcp"]
    created_by: str
    created_at: datetime


class ApplicationListResponse(APIModel):
    applications: list[ApplicationResponse]


class AgentVersionCreateRequest(APIModel):
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    config_snapshot: dict[str, Any] = Field(min_length=1)
    git_commit: str | None = Field(default=None, min_length=1, max_length=128)


class AgentVersionUpdateRequest(APIModel):
    config_snapshot: dict[str, Any] = Field(min_length=1)
    git_commit: str | None = Field(default=None, min_length=1, max_length=128)


class AgentVersionResponse(APIModel):
    agent_version_id: str
    application_id: str
    version: str
    status: Literal["draft", "published"]
    config_snapshot: dict[str, Any]
    git_commit: str | None
    created_by: str
    created_at: datetime
    published_at: datetime | None


class AgentVersionListResponse(APIModel):
    versions: list[AgentVersionResponse]
