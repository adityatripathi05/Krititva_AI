"""Application settings, loaded from environment (pydantic-settings v2).

Env layering: real environment overrides `.env`, which overrides defaults.
Never read `os.environ` directly outside this module.
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_DEFAULT = "insecure-dev-only-change-me"

_log = logging.getLogger("krititva.config")


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
    jwt_secret: str = INSECURE_JWT_DEFAULT  # KRITITVA_JWT_SECRET
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 14
    jwt_algorithm: str = "HS256"
    data_key: str | None = None  # KRITITVA_DATA_KEY: base64, 32 bytes, for at-rest secrets

    # Argon2id parameters (NFR-5.2.1 baselines).
    argon2_memory_kb: int = 65536  # 64 MiB
    argon2_iterations: int = 3
    argon2_parallelism: int = 1

    # CSRF cookie name for browser sessions (NFR-5.2.9).
    csrf_cookie_name: str = "krititva_csrf"
    csrf_header_name: str = "X-CSRF-Token"

    invitation_ttl_days: int = 7

    # Methodology seed templates (packages/methodology-templates/). None → repo default.
    methodology_templates_dir: str | None = None

    # --- OIDC (M0.T3.3 — surface only, actual IdP work deferred) ---
    oidc_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_scopes: str = "openid email profile"

    # --- Telemetry (must default false; see feedback_no_phone_home) ---
    telemetry_enabled: bool = False

    # --- Rate limits ---
    # Per-organization request cap (NFR-5.2.5, §10): at most ``org_rps`` requests
    # per ``rate_limit_window_s`` seconds. Enforced by a Redis fixed-window
    # counter; disabled entirely when ``rate_limit_enabled`` is false or Redis is
    # unavailable (dev/test).
    rate_limit_enabled: bool = True
    org_rps: int = 100
    rate_limit_window_s: int = 1
    user_ai_concurrency: int = 3

    @model_validator(mode="after")
    def _harden_jwt_secret(self) -> Settings:
        """Never run with the world-known default signing secret. In production
        that is a hard boot failure; in dev/test we mint a random ephemeral
        secret so a forgotten ``KRITITVA_JWT_SECRET`` can never yield forgeable
        tokens (the docker/compose path always sets a real secret)."""
        if self.jwt_secret not in ("", INSECURE_JWT_DEFAULT):
            return self
        if self.environment == "production":
            raise ValueError(
                "KRITITVA_JWT_SECRET must be set to a non-default, non-empty value in production"
            )
        self.jwt_secret = secrets.token_urlsafe(48)
        _log.warning(
            "KRITITVA_JWT_SECRET is unset/default; generated an ephemeral secret. "
            "Sessions will not survive a restart — set a stable secret for real use."
        )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance."""
    return Settings()
