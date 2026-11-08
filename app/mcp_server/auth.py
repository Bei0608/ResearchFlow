import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv
from mcp.server.auth.provider import AccessToken

from app.memory.checkpointer import ENV_FILE
from app.security import (
    IdentityRepository,
    JWTSettings,
    decode_mcp_access_token,
    get_identity_repository,
    get_jwt_settings,
)


@dataclass(frozen=True)
class MCPAuthSettings:
    enabled: bool
    issuer_url: str
    resource_server_url: str
    access_token_expire_minutes: int
    required_scopes: list[str]

    def __post_init__(self) -> None:
        if self.access_token_expire_minutes <= 0:
            raise ValueError("MCP Token有效期必须大于0")
        if not self.required_scopes:
            raise ValueError("MCP至少需要一个Scope")


@lru_cache(maxsize=1)
def get_mcp_auth_settings() -> MCPAuthSettings:
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    resource = os.getenv(
        "MCP_RESOURCE_SERVER_URL",
        "http://127.0.0.1:8001/mcp",
    ).rstrip("/")
    audience = os.getenv("MCP_JWT_AUDIENCE", resource).rstrip("/")
    if audience != resource:
        raise RuntimeError(
            "MCP_JWT_AUDIENCE必须与MCP_RESOURCE_SERVER_URL一致"
        )
    scopes = [
        item.strip()
        for item in os.getenv(
            "MCP_REQUIRED_SCOPES",
            "research:read,research:write",
        ).split(",")
        if item.strip()
    ]
    return MCPAuthSettings(
        enabled=os.getenv("MCP_AUTH_ENABLED", "false").lower()
        in {"1", "true", "yes"},
        issuer_url=os.getenv(
            "MCP_ISSUER_URL",
            "http://127.0.0.1:8000",
        ).rstrip("/"),
        resource_server_url=resource,
        access_token_expire_minutes=int(
            os.getenv("MCP_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
        ),
        required_scopes=scopes,
    )


class JWTMCPTokenVerifier:
    """验证ResearchFlow签发且受众绑定到MCP的JWT。"""

    def __init__(
        self,
        settings: MCPAuthSettings,
        repository: IdentityRepository | None = None,
        jwt_settings: JWTSettings | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.jwt_settings = jwt_settings

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            payload = decode_mcp_access_token(
                token,
                self.jwt_settings or get_jwt_settings(),
                self.settings.resource_server_url,
            )
            scopes = payload.get("scope")
            if not isinstance(scopes, list) or not all(
                isinstance(item, str) for item in scopes
            ):
                return None
            if not set(self.settings.required_scopes).issubset(scopes):
                return None
            user_id = str(payload["sub"])
            repository = self.repository or get_identity_repository()
            user = repository.get_user_by_id(user_id)
            if user is None or not user.is_active:
                return None
            return AccessToken(
                token=token,
                client_id="researchflow-user-client",
                scopes=scopes,
                expires_at=int(payload["exp"]),
                resource=self.settings.resource_server_url,
                subject=user_id,
                claims={"iss": str(payload["iss"])},
            )
        except (ValueError, KeyError, TypeError):
            return None
