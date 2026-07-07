"""Argon2id password hashing (NFR-5.2.1)."""

from __future__ import annotations

import pytest

from app.security.hashing import hash_password, needs_rehash, verify_password


def test_hash_and_verify_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_wrong_password() -> None:
    h = hash_password("secret")
    assert verify_password("SECRET", h) is False
    assert verify_password("secret ", h) is False
    assert verify_password("", h) is False


def test_verify_absent_hash_returns_false() -> None:
    """SSO-only users have ``password_hash = NULL``; verify must not crash."""
    assert verify_password("anything", None) is False
    assert verify_password("anything", "") is False


def test_hash_empty_password_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_hash_is_salted() -> None:
    """Two hashes of the same input must differ (salt)."""
    a = hash_password("same-input")
    b = hash_password("same-input")
    assert a != b
    assert verify_password("same-input", a)
    assert verify_password("same-input", b)


def test_needs_rehash_on_invalid_hash() -> None:
    assert needs_rehash("not-a-real-argon2-hash") is True
