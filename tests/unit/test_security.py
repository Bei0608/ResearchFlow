import asyncio

import pytest

from app.mcp_server.auth import (
    JWTMCPTokenVerifier,
    MCPAuthSettings,
)

from app.security import (
    JWTSettings,
    InMemoryIdentityRepository,
    UserRecord,
    create_access_token,
    create_mcp_access_token,
    create_token_pair,
    decode_access_token,
    decode_refresh_token,
)


SETTINGS = JWTSettings(
    secret_key="security-test-secret-key-with-more-than-32-characters",
    access_token_expire_minutes=5,
)
USER = UserRecord(
    user_id="user-123",
    username="bei",
    password_hash="not-used-in-this-test",
)


def test_jwt_round_trip_preserves_identity() -> None:
    token, expires_in = create_access_token(USER, SETTINGS)
    payload = decode_access_token(token, SETTINGS)

    assert payload["sub"] == USER.user_id
    assert payload["username"] == USER.username
    assert expires_in == 300


def test_jwt_rejects_tampered_signature() -> None:
    token, _ = create_access_token(USER, SETTINGS)
    replacement = "a" if token[-1] != "a" else "b"
    tampered = f"{token[:-1]}{replacement}"

    with pytest.raises(ValueError, match="无效或已过期"):
        decode_access_token(tampered, SETTINGS)


def test_jwt_rejects_wrong_audience() -> None:
    token, _ = create_access_token(USER, SETTINGS)
    other_audience = JWTSettings(
        secret_key=SETTINGS.secret_key,
        audience="another-client",
    )

    with pytest.raises(ValueError, match="无效或已过期"):
        decode_access_token(token, other_audience)


def test_access_and_refresh_tokens_are_not_interchangeable() -> None:
    pair = create_token_pair(USER, SETTINGS)

    access_payload = decode_access_token(
        pair.access_token,
        SETTINGS,
    )
    refresh_payload = decode_refresh_token(
        pair.refresh_token,
        SETTINGS,
    )
    assert access_payload["token_type"] == "access"
    assert refresh_payload["token_type"] == "refresh"

    with pytest.raises(ValueError):
        decode_access_token(pair.refresh_token, SETTINGS)
    with pytest.raises(ValueError):
        decode_refresh_token(pair.access_token, SETTINGS)


def test_mcp_token_is_bound_to_resource_and_active_user() -> None:
    repository = InMemoryIdentityRepository()
    user = repository.create_user("mcp-user", "hash")
    mcp_settings = MCPAuthSettings(
        enabled=True,
        issuer_url="https://api.example.com",
        resource_server_url="https://api.example.com/mcp",
        access_token_expire_minutes=15,
        required_scopes=["research:read", "research:write"],
    )
    mcp_token = create_mcp_access_token(
        user,
        SETTINGS,
        resource=mcp_settings.resource_server_url,
        scopes=mcp_settings.required_scopes,
        expire_minutes=15,
    )
    verifier = JWTMCPTokenVerifier(
        mcp_settings,
        repository=repository,
        jwt_settings=SETTINGS,
    )

    verified = asyncio.run(verifier.verify_token(mcp_token.token))
    assert verified is not None
    assert verified.subject == user.user_id
    assert verified.resource == mcp_settings.resource_server_url

    api_token, _ = create_access_token(user, SETTINGS)
    assert asyncio.run(verifier.verify_token(api_token)) is None
def test_explicit_postgres_uri_overrides_dotenv(monkeypatch) -> None:
    from app.memory.checkpointer import get_postgres_uri

    explicit = "postgresql://explicit:secret@localhost/isolated"
    monkeypatch.setenv("POSTGRES_URI", explicit)
    assert get_postgres_uri() == explicit

