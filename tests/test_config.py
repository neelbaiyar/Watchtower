"""Configuration tests that keep example credentials entirely in memory."""

import pytest

from watchtower.config import ConfigurationError, Settings


def test_settings_load_required_environment_values_without_repr_leakage() -> None:
    # Configuration objects can appear in tracebacks or debug output, so secrets
    # must remain usable by code but absent from their default representation.
    settings = Settings.from_environment(
        {
            "WATCHTOWER_SEC_USER_AGENT": "Watchtower test test@example.com",
            "WATCHTOWER_MARKETAUX_API_TOKEN": "private-token",
        }
    )

    assert settings.sec_user_agent == "Watchtower test test@example.com"
    assert settings.marketaux_api_token == "private-token"
    assert settings.snapshot_database_url is None
    assert settings.snapshot_cache_ttl_seconds == 300
    assert "test@example.com" not in repr(settings)
    assert "private-token" not in repr(settings)


def test_settings_report_variable_names_without_values() -> None:
    # Error messages guide setup without reflecting the secret value a user typed.
    with pytest.raises(ConfigurationError) as error:
        Settings.from_environment(
            {
                "WATCHTOWER_SEC_USER_AGENT": "",
                "WATCHTOWER_MARKETAUX_API_TOKEN": "private-token",
            }
        )

    message = str(error.value)
    assert "WATCHTOWER_SEC_USER_AGENT" in message
    assert "private-token" not in message


def test_settings_load_optional_cache_configuration() -> None:
    settings = Settings.from_environment(
        {
            "WATCHTOWER_SEC_USER_AGENT": "Watchtower test test@example.com",
            "WATCHTOWER_MARKETAUX_API_TOKEN": "private-token",
            "WATCHTOWER_SNAPSHOT_DATABASE_URL": "postgres://local-only",
            "WATCHTOWER_SNAPSHOT_CACHE_TTL_SECONDS": "120",
        }
    )

    assert settings.snapshot_database_url == "postgres://local-only"
    assert settings.snapshot_cache_ttl_seconds == 120
    assert "postgres://local-only" not in repr(settings)


@pytest.mark.parametrize("value", ["zero", "0", "-1"])
def test_settings_reject_invalid_cache_ttl(value: str) -> None:
    with pytest.raises(ConfigurationError, match="SNAPSHOT_CACHE_TTL_SECONDS"):
        Settings.from_environment(
            {
                "WATCHTOWER_SEC_USER_AGENT": "Watchtower test test@example.com",
                "WATCHTOWER_MARKETAUX_API_TOKEN": "private-token",
                "WATCHTOWER_SNAPSHOT_CACHE_TTL_SECONDS": value,
            }
        )
