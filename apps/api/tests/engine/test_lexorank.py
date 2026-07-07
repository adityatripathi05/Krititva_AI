"""Lexorank fractional-indexing tests (FR-4.4.7).

Property-based (Hypothesis) per CLAUDE.md §5: the load-bearing invariant is that
`key_between` always yields a key strictly between its neighbours, so any sequence
of insertions keeps the list totally ordered.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engine.lexorank import key_between


def test_seed_key() -> None:
    assert key_between(None, None) == "a0"


def test_append_chain_is_increasing() -> None:
    keys: list[str] = []
    prev: str | None = None
    for _ in range(50):
        prev = key_between(prev, None)
        keys.append(prev)
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


def test_prepend_chain_is_decreasing() -> None:
    keys: list[str] = []
    prev: str | None = None
    for _ in range(50):
        prev = key_between(None, prev)
        keys.append(prev)
    assert keys == sorted(keys, reverse=True)


def test_between_is_strictly_between() -> None:
    a = key_between(None, None)
    b = key_between(a, None)
    mid = key_between(a, b)
    assert a < mid < b


def test_rejects_reversed_bounds() -> None:
    a = key_between(None, None)
    b = key_between(a, None)
    with pytest.raises(ValueError):
        key_between(b, a)


def test_rejects_equal_bounds() -> None:
    a = key_between(None, None)
    with pytest.raises(ValueError):
        key_between(a, a)


@given(
    # A sequence of insertion positions; each value picks an index into the
    # current list (clamped), so we exercise head, tail, and interior inserts.
    st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=200)
)
def test_random_insertions_stay_ordered(positions: list[int]) -> None:
    keys: list[str] = []
    for raw in positions:
        idx = raw % (len(keys) + 1)
        before = keys[idx - 1] if idx > 0 else None
        after = keys[idx] if idx < len(keys) else None
        new_key = key_between(before, after)
        if before is not None:
            assert before < new_key
        if after is not None:
            assert new_key < after
        keys.insert(idx, new_key)
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
