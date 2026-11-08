from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pwdlib import PasswordHash

from app.api.dependencies import (
    get_current_user,
    provide_identity_repository,
    provide_jwt_settings,
    provide_workspace_repository,
)
from app.api.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    RegisterRequest,
    RefreshTokenRequest,
    LogoutResponse,
    MCPTokenResponse,
    TokenResponse,
    UserResponse,
)
from app.security.audit import record_audit_event
from app.security import (
    DuplicateUsernameError,
    IdentityRepository,
    JWTSettings,
    UserRecord,
    create_token_pair,
    create_mcp_access_token,
    decode_refresh_token,
)
from app.mcp_server.auth import get_mcp_auth_settings
from app.workspaces import WorkspaceRepository


router = APIRouter(prefix="/auth", tags=["auth"])
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("researchflow-dummy-password")


def to_user_response(user: UserRecord) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        is_active=user.is_active,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    http_request: Request,
    request: RegisterRequest,
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
    workspace_repository: Annotated[
        WorkspaceRepository,
        Depends(provide_workspace_repository),
    ],
) -> UserResponse:
    """注册本地用户，密码只以Argon2哈希形式保存。"""
    try:
        user = repository.create_user(
            username=request.username,
            password_hash=password_hash.hash(
                request.password
            ),
        )
    except DuplicateUsernameError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        ) from None
    workspace = workspace_repository.ensure_personal_workspace(
        user.user_id,
        user.username,
    )
    record_audit_event(
        repository,
        http_request,
        user_id=user.user_id,
        event_type="user.registered",
        resource="user",
        metadata={"workspace_id": workspace.workspace_id},
    )
    return to_user_response(user)


@router.post("/token", response_model=TokenResponse)
def login(
    request: Request,
    form: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
    settings: Annotated[
        JWTSettings,
        Depends(provide_jwt_settings),
    ],
) -> TokenResponse:
    """使用OAuth2密码流换取短期JWT访问令牌。"""
    user = repository.get_user_by_username(form.username)
    stored_hash = (
        user.password_hash if user is not None else DUMMY_HASH
    )
    password_valid = password_hash.verify(
        form.password,
        stored_hash,
    )

    if (
        user is None
        or not password_valid
        or not user.is_active
    ):
        record_audit_event(
            repository,
            request,
            user_id=user.user_id if user is not None else None,
            event_type="auth.login",
            resource="access_token",
            outcome="failure",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    pair = create_token_pair(user, settings)
    repository.create_refresh_session(
        token_id=pair.refresh_jti,
        user_id=user.user_id,
        expires_at=pair.refresh_expires_at,
    )
    record_audit_event(
        repository,
        request,
        user_id=user.user_id,
        event_type="auth.login",
        resource="access_token",
    )
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.access_expires_in,
        refresh_token=pair.refresh_token,
        refresh_expires_in=pair.refresh_expires_in,
    )


def _decode_refresh_or_unauthorized(
    token: str,
    settings: JWTSettings,
) -> dict[str, object]:
    try:
        return decode_refresh_token(token, settings)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的刷新令牌",
        ) from None


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(
    http_request: Request,
    request: RefreshTokenRequest,
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
    settings: Annotated[
        JWTSettings,
        Depends(provide_jwt_settings),
    ],
) -> TokenResponse:
    """轮换Refresh Token并签发新的Token对。"""
    payload = _decode_refresh_or_unauthorized(
        request.refresh_token,
        settings,
    )
    user_id = str(payload["sub"])
    old_token_id = str(payload["jti"])
    user = repository.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不可用",
        )

    pair = create_token_pair(user, settings)
    rotated = repository.rotate_refresh_session(
        old_token_id=old_token_id,
        new_token_id=pair.refresh_jti,
        user_id=user_id,
        expires_at=pair.refresh_expires_at,
    )
    if not rotated:
        record_audit_event(
            repository,
            http_request,
            user_id=user_id,
            event_type="auth.refresh",
            resource="refresh_token",
            outcome="failure",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌已使用、已撤销或已过期",
        )
    record_audit_event(
        repository,
        http_request,
        user_id=user_id,
        event_type="auth.refresh",
        resource="refresh_token",
    )
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.access_expires_in,
        refresh_token=pair.refresh_token,
        refresh_expires_in=pair.refresh_expires_in,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    http_request: Request,
    request: RefreshTokenRequest,
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
    settings: Annotated[
        JWTSettings,
        Depends(provide_jwt_settings),
    ],
) -> LogoutResponse:
    """撤销指定Refresh Token。"""
    payload = _decode_refresh_or_unauthorized(
        request.refresh_token,
        settings,
    )
    revoked = repository.revoke_refresh_session(
        token_id=str(payload["jti"]),
        user_id=str(payload["sub"]),
    )
    record_audit_event(
        repository,
        http_request,
        user_id=str(payload["sub"]),
        event_type="auth.logout",
        resource="refresh_token",
        outcome="success" if revoked else "noop",
    )
    return LogoutResponse(revoked=revoked)


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
)
def change_password(
    http_request: Request,
    request: ChangePasswordRequest,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
) -> ChangePasswordResponse:
    """验证旧密码后更新密码，并撤销该用户全部Refresh会话。"""
    if not password_hash.verify(
        request.current_password,
        user.password_hash,
    ):
        record_audit_event(
            repository,
            http_request,
            user_id=user.user_id,
            event_type="auth.password_change",
            resource="user",
            outcome="failure",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前密码错误",
        )
    if request.current_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与当前密码相同",
        )
    changed = repository.update_password(
        user.user_id,
        password_hash.hash(request.new_password),
    )
    if not changed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="密码更新失败",
        )
    revoked = repository.revoke_all_refresh_sessions(
        user.user_id
    )
    record_audit_event(
        repository,
        http_request,
        user_id=user.user_id,
        event_type="auth.password_change",
        resource="user",
        metadata={"revoked_refresh_sessions": revoked},
    )
    return ChangePasswordResponse(
        changed=True,
        revoked_refresh_sessions=revoked,
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    user: Annotated[UserRecord, Depends(get_current_user)],
) -> UserResponse:
    """返回JWT对应的当前用户。"""
    return to_user_response(user)


@router.post("/mcp-token", response_model=MCPTokenResponse)
def issue_mcp_token(
    http_request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[
        IdentityRepository,
        Depends(provide_identity_repository),
    ],
    settings: Annotated[
        JWTSettings,
        Depends(provide_jwt_settings),
    ],
) -> MCPTokenResponse:
    """把当前API身份交换为受众绑定的短期MCP访问令牌。"""
    mcp_settings = get_mcp_auth_settings()
    token = create_mcp_access_token(
        user,
        settings,
        resource=mcp_settings.resource_server_url,
        scopes=mcp_settings.required_scopes,
        expire_minutes=mcp_settings.access_token_expire_minutes,
    )
    record_audit_event(
        repository,
        http_request,
        user_id=user.user_id,
        event_type="auth.mcp_token_issued",
        resource=mcp_settings.resource_server_url,
        metadata={"scopes": token.scopes},
    )
    return MCPTokenResponse(
        access_token=token.token,
        expires_in=token.expires_in,
        scope=" ".join(token.scopes),
        resource=token.resource,
    )
