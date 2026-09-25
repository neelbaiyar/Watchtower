"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is unavailable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated Watchtower settings whose values are excluded from repr output."""

    sec_user_agent: str = field(repr=False)
    marketaux_api_token: str = field(repr=False)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> Settings:
        values = environment if environment is not None else os.environ
        required = {
            "WATCHTOWER_SEC_USER_AGENT": values.get(
                "WATCHTOWER_SEC_USER_AGENT", ""
            ).strip(),
            "WATCHTOWER_MARKETAUX_API_TOKEN": values.get(
                "WATCHTOWER_MARKETAUX_API_TOKEN", ""
            ).strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            names = ", ".join(missing)
            raise ConfigurationError(f"Missing required environment variables: {names}")

        return cls(
            sec_user_agent=required["WATCHTOWER_SEC_USER_AGENT"],
            marketaux_api_token=required["WATCHTOWER_MARKETAUX_API_TOKEN"],
        )
