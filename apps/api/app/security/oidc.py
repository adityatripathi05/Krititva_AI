"""OIDC (Authlib) surface — feature-flagged (§FR-4.1.2).

v1 self-host defaults ``oidc_enabled=False``. The actual login-flow integration
lands post-M0.T3 (guarded by this settings surface). This module exposes the
typed config check + a factory so downstream code stays uncluttered by feature
gating.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True, slots=True)
class OIDCConfig:
    issuer: str
    client_id: str
    client_secret: str
    scopes: str


def oidc_enabled() -> bool:
    return get_settings().oidc_enabled


def get_oidc_config() -> OIDCConfig | None:
    """Return the OIDC config or ``None`` when the feature is disabled or unset."""
    s = get_settings()
    if not s.oidc_enabled:
        return None
    if not (s.oidc_issuer and s.oidc_client_id and s.oidc_client_secret):
        return None
    return OIDCConfig(
        issuer=s.oidc_issuer,
        client_id=s.oidc_client_id,
        client_secret=s.oidc_client_secret,
        scopes=s.oidc_scopes,
    )
