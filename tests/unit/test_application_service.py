import pytest

from app.applications import SensitiveConfigError, prepare_config_snapshot


@pytest.mark.parametrize(
    "config",
    [
        {"api_key": "secret"},
        {"provider": {"access_token": "secret"}},
        {"headers": {"Authorization": "Bearer secret"}},
        {"database": {"password": "secret"}},
        {"items": [{"private-key": "secret"}]},
    ],
)
def test_prepare_config_snapshot_rejects_sensitive_fields(config: dict) -> None:
    with pytest.raises(SensitiveConfigError, match="敏感字段") as error:
        prepare_config_snapshot(config)

    assert "secret" not in str(error.value)


def test_prepare_config_snapshot_allows_non_secret_token_settings() -> None:
    snapshot = prepare_config_snapshot(
        {
            "schema_version": "1.0",
            "model": {"max_tokens": 1024},
            "limits": {"token_limit": 4096},
        }
    )

    assert snapshot["model"]["max_tokens"] == 1024
    assert snapshot["limits"]["token_limit"] == 4096


def test_prepare_config_snapshot_is_detached_from_request() -> None:
    config = {"schema_version": "1.0", "retrieval": {"top_k": 5}}

    snapshot = prepare_config_snapshot(config)
    config["retrieval"]["top_k"] = 99

    assert snapshot["retrieval"]["top_k"] == 5
