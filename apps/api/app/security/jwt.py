"""JWT access-token encoding (NFR-5.2.2).

Refresh tokens are OPAQUE (see ``app.services.auth``) — this module only
concerns the short-lived access JWT the API bearer-authenticates against.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from jose import JWTError, jwt

from app.config import get_settings


class InvalidToken(Exception):
    """Raised when a token is missing, malformed, expired, or has the wrong type."""


def _now() -> datetime:
    return datetime.now(UTC)


def encode_access_token(user_id: uuid.UUID) -> str:
    """Return a signed access JWT for ``user_id``.

    Claims are intentionally minimal (sub, type, iat, exp, jti). Everything else
    the request handler needs is resolved via a DB lookup keyed off ``sub`` — see
    ``app.api.deps.get_current_user``.
    """
    s = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_access_ttl_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    """Return the ``sub`` UUID from a valid access token; raise ``InvalidToken`` otherwise."""
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except JWTError as exc:
        raise InvalidToken(str(exc)) from exc

    if payload.get("type") != "access":
        raise InvalidToken("wrong token type")
    try:
        return uuid.UUID(cast(str, payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise InvalidToken("malformed sub") from exc


# ---------------------------------------------------------------------------
# Opaque refresh + invitation tokens
# ---------------------------------------------------------------------------


def new_opaque_token(nbytes: int = 32) -> str:
    """URL-safe opaque token used for refresh / invitation flows."""
    return secrets.token_urlsafe(nbytes)


def hash_opaque_token(token: str) -> str:
    """SHA-256 the token so DB rows never carry the raw secret."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
