import pytest

from watchtower.config import ConfigurationError, Settings


def test_settings_load_required_environment_values_without_repr_leakage() -> None:
    settings = Settings.from_environment(
        {
            "WATCHTOWER_SEC_USER_AGENT": "Watchtower test test@example.com",
            "WATCHTOWER_MARKETAUX_API_TOKEN": "private-token",
        }
    )

    assert settings.sec_user_agent == "Watchtower test test@example.com"
    assert settings.marketaux_api_token == "private-token"
    assert "test@example.com" not in repr(settings)
    assert "private-token" not in repr(settings)


def test_settings_report_variable_names_without_values() -> None:
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
