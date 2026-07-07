"""Argon2id password hashing (NFR-5.2.1)."""

from __future__ import annotations

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import get_settings

_hasher: PasswordHasher | None = None


def _get_hasher() -> PasswordHasher:
    global _hasher
    if _hasher is None:
        s = get_settings()
        _hasher = PasswordHasher(
            memory_cost=s.argon2_memory_kb,
            time_cost=s.argon2_iterations,
            parallelism=s.argon2_parallelism,
            hash_len=32,
            salt_len=16,
        )
    return _hasher


def hash_password(raw: str) -> str:
    """Hash a plaintext password. Empty strings are rejected."""
    if not raw:
        raise ValueError("password must be non-empty")
    return _get_hasher().hash(raw)


def verify_password(raw: str, hashed: str | None) -> bool:
    """Constant-time verify. Returns False for absent hash (SSO-only users).

    Returns True and silently rehashes if params drift below current settings —
    rehash upgrades are the caller's responsibility to persist.
    """
    if not hashed:
        return False
    try:
        _get_hasher().verify(hashed, raw)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return True


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _get_hasher().hash("timing-equalizer")


def verify_dummy(raw: str) -> None:
    """Verify against a throwaway hash to equalize login timing for non-existent
    users, closing the user-enumeration timing oracle (NFR-5.2.x)."""
    verify_password(raw, _dummy_hash())


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash's params fall below the current policy."""
    try:
        return _get_hasher().check_needs_rehash(hashed)
    except InvalidHashError:
        return True
