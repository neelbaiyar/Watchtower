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
    # Database caching is opt-in so the basic local API remains usable without
    # Docker. Its URL is never included in repr output.
    snapshot_database_url: str | None = field(default=None, repr=False)
    snapshot_cache_ttl_seconds: int = 300

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> Settings:
        # Tests pass a tiny dictionary here; production reads the process
        # environment populated from the ignored local .env file.
        values = environment if environment is not None else os.environ
        required = {
            "WATCHTOWER_SEC_USER_AGENT": values.get(
                "WATCHTOWER_SEC_USER_AGENT", ""
            ).strip(),
            "WATCHTOWER_MARKETAUX_API_TOKEN": values.get(
                "WATCHTOWER_MARKETAUX_API_TOKEN", ""
            ).strip(),
        }
        # Validate all required settings together so startup reports every
        # missing value without ever printing a secret value.
        missing = [name for name, value in required.items() if not value]
        if missing:
            names = ", ".join(missing)
            raise ConfigurationError(f"Missing required environment variables: {names}")

        database_url = values.get("WATCHTOWER_SNAPSHOT_DATABASE_URL", "").strip()
        ttl_value = values.get("WATCHTOWER_SNAPSHOT_CACHE_TTL_SECONDS", "300").strip()
        try:
            cache_ttl_seconds = int(ttl_value)
        except ValueError as error:
            raise ConfigurationError(
                "WATCHTOWER_SNAPSHOT_CACHE_TTL_SECONDS must be a whole number"
            ) from error
        if cache_ttl_seconds <= 0:
            raise ConfigurationError(
                "WATCHTOWER_SNAPSHOT_CACHE_TTL_SECONDS must be greater than zero"
            )

        return cls(
            sec_user_agent=required["WATCHTOWER_SEC_USER_AGENT"],
            marketaux_api_token=required["WATCHTOWER_MARKETAUX_API_TOKEN"],
            snapshot_database_url=database_url or None,
            snapshot_cache_ttl_seconds=cache_ttl_seconds,
        )
