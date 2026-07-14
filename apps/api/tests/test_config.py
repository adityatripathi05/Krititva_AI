"""JWT signing-secret hardening (review finding #3; NFR-5.2.2, §10).

The world-known default secret must never sign tokens in a running server:
a hard boot failure in production, an ephemeral random secret elsewhere.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import INSECURE_JWT_DEFAULT, Settings


def _settings(**kw: object) -> Settings:
    # _env_file=None so a stray .env can't inject a real secret and mask the test.
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValidationError):
        _settings(environment="production", jwt_secret=INSECURE_JWT_DEFAULT)


def test_production_rejects_empty_secret() -> None:
    with pytest.raises(ValidationError):
        _settings(environment="production", jwt_secret="")


def test_dev_mints_ephemeral_secret() -> None:
    s = _settings(environment="development", jwt_secret=INSECURE_JWT_DEFAULT)
    assert s.jwt_secret not in ("", INSECURE_JWT_DEFAULT)
    assert len(s.jwt_secret) >= 32


def test_explicit_secret_is_preserved() -> None:
    s = _settings(environment="production", jwt_secret="a-real-and-sufficiently-long-secret")
    assert s.jwt_secret == "a-real-and-sufficiently-long-secret"
