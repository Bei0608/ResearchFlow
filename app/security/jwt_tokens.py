import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import uuid4

import jwt
from dotenv import load_dotenv
from jwt.exceptions import InvalidTokenError

from app.memory.checkpointer import ENV_FILE
from app.security.repository import UserRecord


@dataclass(frozen=True)
class JWTSettings:
    """JWT签发和验证配置。"""

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    issuer: str = "researchflow-api"
    audience: str = "researchflow-client"

    def __post_init__(self) -> None:
        if len(self.secret_key) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY至少需要32个字符"
            )
        if self.algorithm != "HS256":
            raise RuntimeError(
                "当前版本仅允许JWT_ALGORITHM=HS256"
            )
        if self.access_token_expire_minutes <= 0:
            raise RuntimeError(
                "JWT_ACCESS_TOKEN_EXPIRE_MINUTES必须大于0"
            )
        if self.refresh_token_expire_days <= 0:
            raise RuntimeError(
                "JWT_REFRESH_TOKEN_EXPIRE_DAYS必须大于0"
            )


@dataclass(frozen=True)
class TokenPair:
    """一次登录或刷新产生的Token对。"""

    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int
    refresh_jti: str
    refresh_expires_at: datetime


@dataclass(frozen=True)
class MCPAccessToken:
    token: str
    expires_in: int
    expires_at: datetime
    scopes: list[str]
    resource: str


@lru_cache(maxsize=1)
def get_jwt_settings() -> JWTSettings:
    """从环境变量加载JWT配置。"""
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    secret_key = os.getenv("JWT_SECRET_KEY", "")

    if not secret_key:
        raise RuntimeError(
            f"缺少JWT_SECRET_KEY，请检查：{ENV_FILE}"
        )

    return JWTSettings(
        secret_key=secret_key,
        algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=int(
            os.getenv(
                "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
                "60",
            )
        ),
        refresh_token_expire_days=int(
            os.getenv(
                "JWT_REFRESH_TOKEN_EXPIRE_DAYS",
                "7",
            )
        ),
        issuer=os.getenv("JWT_ISSUER", "researchflow-api"),
        audience=os.getenv(
            "JWT_AUDIENCE",
            "researchflow-client",
        ),
    )


def create_access_token(
    user: UserRecord,
    settings: JWTSettings,
) -> tuple[str, int]:
    """为已认证用户签发短期访问令牌。"""
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(
        minutes=settings.access_token_expire_minutes
    )
    expires_at = now + expires_delta
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "iat": now,
        "exp": expires_at,
        "jti": uuid4().hex,
        "iss": settings.issuer,
        "aud": settings.audience,
        "token_type": "access",
    }
    token = jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return token, int(expires_delta.total_seconds())


def create_token_pair(
    user: UserRecord,
    settings: JWTSettings,
) -> TokenPair:
    """签发Access Token与可轮换Refresh Token。"""
    access_token, access_expires_in = create_access_token(
        user,
        settings,
    )
    now = datetime.now(timezone.utc)
    refresh_delta = timedelta(
        days=settings.refresh_token_expire_days
    )
    refresh_expires_at = now + refresh_delta
    refresh_jti = uuid4().hex
    refresh_payload = {
        "sub": user.user_id,
        "username": user.username,
        "iat": now,
        "exp": refresh_expires_at,
        "jti": refresh_jti,
        "iss": settings.issuer,
        "aud": settings.audience,
        "token_type": "refresh",
    }
    refresh_token = jwt.encode(
        refresh_payload,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return TokenPair(
        access_token=access_token,
        access_expires_in=access_expires_in,
        refresh_token=refresh_token,
        refresh_expires_in=int(refresh_delta.total_seconds()),
        refresh_jti=refresh_jti,
        refresh_expires_at=refresh_expires_at,
    )


def create_mcp_access_token(
    user: UserRecord,
    settings: JWTSettings,
    *,
    resource: str,
    scopes: list[str],
    expire_minutes: int,
) -> MCPAccessToken:
    """签发仅能用于指定MCP资源服务器的短期Token。"""
    if expire_minutes <= 0:
        raise ValueError("MCP Token有效期必须大于0")
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=expire_minutes)
    expires_at = now + expires_delta
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "iat": now,
        "exp": expires_at,
        "jti": uuid4().hex,
        "iss": settings.issuer,
        "aud": resource,
        "token_type": "mcp_access",
        "scope": scopes,
    }
    token = jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return MCPAccessToken(
        token=token,
        expires_in=int(expires_delta.total_seconds()),
        expires_at=expires_at,
        scopes=scopes,
        resource=resource,
    )


def decode_token(
    token: str,
    settings: JWTSettings,
    expected_type: str,
) -> dict[str, object]:
    """验证JWT及其Access/Refresh用途。"""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            audience=settings.audience,
            issuer=settings.issuer,
            options={
                "require": [
                    "sub",
                    "iat",
                    "exp",
                    "jti",
                    "iss",
                    "aud",
                    "token_type",
                ]
            },
        )
        if payload.get("token_type") != expected_type:
            raise ValueError("Token用途不正确")
        return payload
    except InvalidTokenError as exception:
        raise ValueError("无效或已过期的访问令牌") from exception


def decode_access_token(
    token: str,
    settings: JWTSettings,
) -> dict[str, object]:
    """验证Access Token。"""
    return decode_token(token, settings, "access")


def decode_refresh_token(
    token: str,
    settings: JWTSettings,
) -> dict[str, object]:
    """验证Refresh Token。"""
    try:
        return decode_token(token, settings, "refresh")
    except ValueError as exception:
        raise ValueError("无效或已过期的刷新令牌") from exception


def decode_mcp_access_token(
    token: str,
    settings: JWTSettings,
    resource: str,
) -> dict[str, object]:
    """验证MCP专用Token及其资源受众。"""
    resource_settings = replace(settings, audience=resource)
    return decode_token(
        token,
        resource_settings,
        "mcp_access",
    )
