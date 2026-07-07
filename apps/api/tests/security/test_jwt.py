"""JWT access-token encoding + opaque-token helpers."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.config import get_settings
from app.security.jwt import (
    InvalidToken,
    decode_access_token,
    encode_access_token,
    hash_opaque_token,
    new_opaque_token,
)


def test_encode_decode_roundtrip() -> None:
    uid = uuid.uuid4()
    token = encode_access_token(uid)
    assert decode_access_token(token) == uid


def test_decode_malformed_token_raises() -> None:
    with pytest.raises(InvalidToken):
        decode_access_token("not-a-jwt")


def test_decode_wrong_signature_raises() -> None:
    s = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
    }
    tampered = jwt.encode(payload, "wrong-secret", algorithm=s.jwt_algorithm)
    with pytest.raises(InvalidToken):
        decode_access_token(tampered)


def test_decode_wrong_type_raises() -> None:
    s = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "refresh",  # wrong kind
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
    }
    tok = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    with pytest.raises(InvalidToken):
        decode_access_token(tok)


def test_decode_expired_raises() -> None:
    s = get_settings()
    past = datetime.now(UTC) - timedelta(hours=1)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": int(past.timestamp()),
        "exp": int(past.timestamp()) + 60,
    }
    tok = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    with pytest.raises(InvalidToken):
        decode_access_token(tok)


def test_new_opaque_tokens_are_unique() -> None:
    a = new_opaque_token()
    b = new_opaque_token()
    assert a != b
    assert len(a) >= 32


def test_hash_opaque_deterministic() -> None:
    t = new_opaque_token()
    assert hash_opaque_token(t) == hash_opaque_token(t)
    assert hash_opaque_token(t) != t  # not the raw
