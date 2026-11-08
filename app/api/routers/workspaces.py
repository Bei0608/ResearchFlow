from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import (
    get_current_user,
    provide_application_repository,
    provide_identity_repository,
    provide_workspace_repository,
)
from app.api.workspace_schemas import (
    AgentVersionCreateRequest,
    AgentVersionListResponse,
    AgentVersionResponse,
    AgentVersionUpdateRequest,
    ApplicationCreateRequest,
    ApplicationListResponse,
    ApplicationResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
    ReviewerAddRequest,
)
from app.applications import (
    AgentVersionRecord,
    ApplicationRecord,
    ApplicationRepository,
    DuplicateAgentVersionError,
    DuplicateApplicationError,
    ImmutableAgentVersionError,
    SensitiveConfigError,
    prepare_config_snapshot,
)
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event
from app.workspaces import WorkspaceRecord, WorkspaceRepository


router = APIRouter(tags=["evaluation-platform"])


@router.post(
    "/workspaces/{workspace_id}/reviewers",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_workspace_reviewer(
    workspace_id: str,
    payload: ReviewerAddRequest,
    request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
    workspace_repository: Annotated[WorkspaceRepository, Depends(provide_workspace_repository)],
    identity_repository: Annotated[IdentityRepository, Depends(provide_identity_repository)],
) -> WorkspaceResponse:
    reviewer = identity_repository.get_user_by_username(payload.username)
    if reviewer is None or not reviewer.is_active:
        raise HTTPException(status_code=404, detail="用户不存在")
    record = workspace_repository.add_reviewer(
        workspace_id, user.user_id, reviewer.user_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Workspace不存在")
    record_audit_event(
        identity_repository,
        request,
        user_id=user.user_id,
        event_type="workspace.reviewer_added",
        resource=workspace_id,
        metadata={"reviewer_id": reviewer.user_id},
    )
    return _workspace_response(record)


def _workspace_response(record: WorkspaceRecord) -> WorkspaceResponse:
    return WorkspaceResponse(**record.__dict__)


def _application_response(record: ApplicationRecord) -> ApplicationResponse:
    return ApplicationResponse(**record.__dict__)


def _version_response(record: AgentVersionRecord) -> AgentVersionResponse:
    return AgentVersionResponse(**record.__dict__)


def _prepare_snapshot(config: dict) -> dict:
    try:
        return prepare_config_snapshot(config)
    except SensitiveConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None


def _require_application(
    repository: ApplicationRepository,
    application_id: str,
    user_id: str,
) -> ApplicationRecord:
    application = repository.get_application(application_id, user_id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent应用不存在",
        )
    return application


@router.get("/workspaces", response_model=WorkspaceListResponse)
def list_workspaces(
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        WorkspaceRepository,
        Depends(provide_workspace_repository),
    ],
) -> WorkspaceListResponse:
    repository.ensure_personal_workspace(user.user_id, user.username)
    return WorkspaceListResponse(
        workspaces=[
            _workspace_response(item)
            for item in repository.list_workspaces(user.user_id)
        ]
    )


@router.post(
    "/workspaces/{workspace_id}/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_application(
    workspace_id: str,
    payload: ApplicationCreateRequest,
    request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        ApplicationRepository,
        Depends(provide_application_repository),
    ],
    identity_repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> ApplicationResponse:
    try:
        application = repository.create_application(
            workspace_id=workspace_id,
            user_id=user.user_id,
            name=payload.name,
            description=payload.description,
            target_type=payload.target_type,
        )
    except DuplicateApplicationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace中已存在同名应用",
        ) from None
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace不存在",
        )
    record_audit_event(
        identity_repository,
        request,
        user_id=user.user_id,
        event_type="application.created",
        resource=application.application_id,
        metadata={"workspace_id": workspace_id},
    )
    return _application_response(application)


@router.get(
    "/workspaces/{workspace_id}/applications",
    response_model=ApplicationListResponse,
)
def list_applications(
    workspace_id: str,
    user: Annotated[UserRecord, Depends(get_current_user)],
    workspace_repository: Annotated[
        WorkspaceRepository,
        Depends(provide_workspace_repository),
    ],
    repository: Annotated[
        ApplicationRepository,
        Depends(provide_application_repository),
    ],
) -> ApplicationListResponse:
    if workspace_repository.get_workspace_for_user(
        workspace_id,
        user.user_id,
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace不存在",
        )
    return ApplicationListResponse(
        applications=[
            _application_response(item)
            for item in repository.list_applications(
                workspace_id,
                user.user_id,
            )
        ]
    )


@router.post(
    "/applications/{application_id}/versions",
    response_model=AgentVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_version(
    application_id: str,
    payload: AgentVersionCreateRequest,
    request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        ApplicationRepository,
        Depends(provide_application_repository),
    ],
    identity_repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> AgentVersionResponse:
    snapshot = _prepare_snapshot(payload.config_snapshot)
    try:
        version = repository.create_version(
            application_id=application_id,
            user_id=user.user_id,
            version=payload.version,
            config_snapshot=snapshot,
            git_commit=payload.git_commit,
        )
    except DuplicateAgentVersionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="应用中已存在相同版本号",
        ) from None
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent应用不存在",
        )
    record_audit_event(
        identity_repository,
        request,
        user_id=user.user_id,
        event_type="agent_version.created",
        resource=version.agent_version_id,
        metadata={
            "application_id": application_id,
            "version": version.version,
        },
    )
    return _version_response(version)


@router.get(
    "/applications/{application_id}/versions",
    response_model=AgentVersionListResponse,
)
def list_agent_versions(
    application_id: str,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        ApplicationRepository,
        Depends(provide_application_repository),
    ],
) -> AgentVersionListResponse:
    _require_application(repository, application_id, user.user_id)
    return AgentVersionListResponse(
        versions=[
            _version_response(item)
            for item in repository.list_versions(
                application_id,
                user.user_id,
            )
        ]
    )


@router.put(
    "/applications/{application_id}/versions/{agent_version_id}",
    response_model=AgentVersionResponse,
)
def update_agent_version(
    application_id: str,
    agent_version_id: str,
    payload: AgentVersionUpdateRequest,
    request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        ApplicationRepository,
        Depends(provide_application_repository),
    ],
    identity_repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> AgentVersionResponse:
    snapshot = _prepare_snapshot(payload.config_snapshot)
    try:
        version = repository.update_version(
            application_id=application_id,
            agent_version_id=agent_version_id,
            user_id=user.user_id,
            config_snapshot=snapshot,
            git_commit=payload.git_commit,
        )
    except ImmutableAgentVersionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已发布版本不可修改；请创建新版本",
        ) from None
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent版本不存在",
        )
    record_audit_event(
        identity_repository,
        request,
        user_id=user.user_id,
        event_type="agent_version.updated",
        resource=version.agent_version_id,
        metadata={"application_id": application_id},
    )
    return _version_response(version)


@router.post(
    "/applications/{application_id}/versions/{agent_version_id}/publish",
    response_model=AgentVersionResponse,
)
def publish_agent_version(
    application_id: str,
    agent_version_id: str,
    request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        ApplicationRepository,
        Depends(provide_application_repository),
    ],
    identity_repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> AgentVersionResponse:
    version = repository.publish_version(
        application_id,
        agent_version_id,
        user.user_id,
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent版本不存在",
        )
    record_audit_event(
        identity_repository,
        request,
        user_id=user.user_id,
        event_type="agent_version.published",
        resource=version.agent_version_id,
        metadata={
            "application_id": application_id,
            "version": version.version,
        },
    )
    return _version_response(version)
