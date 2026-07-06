"""Application settings, loaded from environment (pydantic-settings v2).

Env layering: real environment overrides `.env`, which overrides defaults.
Never read `os.environ` directly outside this module.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Populated via env vars prefixed with ``KRITITVA_``, except the well-known
    ``POSTGRES_DSN`` / ``REDIS_URL`` / ``LITELLM_URL`` which are read as-is.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="KRITITVA_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    # --- Server ---
    public_base_url: str = "http://localhost:8000"
    api_prefix: str = "/api/v1"

    # --- Data (unprefixed for docker/compose convention) ---
    postgres_dsn: str = Field(
        default="postgresql+asyncpg://krititva:krititva@localhost:5432/krititva",
        alias="POSTGRES_DSN",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- LLM gateway ---
    litellm_url: str = Field(default="http://localhost:4000", alias="LITELLM_URL")

    # --- Security ---
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 14
    data_key: str | None = None  # KRITITVA_DATA_KEY: base64, 32 bytes, for at-rest secrets

    # --- Telemetry (must default false; see feedback_no_phone_home) ---
    telemetry_enabled: bool = False

    # --- Rate limits ---
    org_rps: int = 100
    user_ai_concurrency: int = 3


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance."""
    return Settings()
