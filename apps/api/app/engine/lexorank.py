"""Fractional indexing for backlog/board ordering (FR-4.4.7).

An implementation of the well-known jitter-free fractional-indexing algorithm
(Greenspan / rocicorp). Keys are base-62 strings ordered lexicographically;
``key_between(a, b)`` returns a key strictly between ``a`` and ``b`` (either may
be ``None`` for an open end). Inserting only ever writes the single moved row —
no neighbours are touched — so rebalancing is O(1) amortized on one row.

Key layout: an integer part (a length-prefixed magnitude header) followed by a
fractional part. The integer header lets the sequence grow unbounded at either
end in O(1); the fractional part fills the gaps between adjacent keys.
"""

from __future__ import annotations

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_SMALLEST_INTEGER = "A00000000000000000000000000"
_INTEGER_ZERO = "a0"


def _integer_length(head: str) -> int:
    if "a" <= head <= "z":
        return ord(head) - ord("a") + 2
    if "A" <= head <= "Z":
        return ord("Z") - ord(head) + 2
    raise ValueError(f"invalid order-key head: {head!r}")


def _integer_part(key: str) -> str:
    length = _integer_length(key[0])
    if length > len(key):
        raise ValueError(f"invalid order key: {key!r}")
    return key[:length]


def _validate_integer(part: str) -> None:
    if len(part) != _integer_length(part[0]):
        raise ValueError(f"invalid integer part of order key: {part!r}")


def _validate_order_key(key: str) -> None:
    if key == _SMALLEST_INTEGER:
        raise ValueError(f"invalid order key: {key!r}")
    integer = _integer_part(key)
    frac = key[len(integer) :]
    if frac.endswith(DIGITS[0]):
        raise ValueError(f"invalid order key (trailing zero): {key!r}")


def _increment_integer(x: str) -> str | None:
    _validate_integer(x)
    head, digs = x[0], list(x[1:])
    carry = True
    for i in range(len(digs) - 1, -1, -1):
        if not carry:
            break
        d = DIGITS.index(digs[i]) + 1
        if d == len(DIGITS):
            digs[i] = DIGITS[0]
        else:
            digs[i] = DIGITS[d]
            carry = False
    if carry:
        if head == "Z":
            return "a" + DIGITS[0]
        if head == "z":
            return None
        h = chr(ord(head) + 1)
        if h > "a":
            digs.append(DIGITS[0])
        else:
            digs.pop()
        return h + "".join(digs)
    return head + "".join(digs)


def _decrement_integer(x: str) -> str | None:
    _validate_integer(x)
    head, digs = x[0], list(x[1:])
    borrow = True
    for i in range(len(digs) - 1, -1, -1):
        if not borrow:
            break
        d = DIGITS.index(digs[i]) - 1
        if d == -1:
            digs[i] = DIGITS[-1]
        else:
            digs[i] = DIGITS[d]
            borrow = False
    if borrow:
        if head == "a":
            return "Z" + DIGITS[-1]
        if head == "A":
            return None
        h = chr(ord(head) - 1)
        if h < "Z":
            digs.append(DIGITS[-1])
        else:
            digs.pop()
        return h + "".join(digs)
    return head + "".join(digs)


def _midpoint(a: str, b: str | None) -> str:
    """Return a fractional string strictly between ``a`` and ``b`` (a < b)."""
    zero = DIGITS[0]
    if b is not None and a >= b:
        raise ValueError(f"{a!r} >= {b!r}")
    if a.endswith(zero) or (b is not None and b.endswith(zero)):
        raise ValueError("trailing zero")
    if b is not None:
        n = 0
        while (a[n] if n < len(a) else zero) == (b[n] if n < len(b) else None):
            n += 1
        if n > 0:
            return b[:n] + _midpoint(a[n:], b[n:])
    digit_a = DIGITS.index(a[0]) if a else 0
    digit_b = DIGITS.index(b[0]) if (b is not None and b) else len(DIGITS)
    if digit_b - digit_a > 1:
        mid = round(0.5 * (digit_a + digit_b))
        return DIGITS[mid]
    if b is not None and len(b) > 1:
        return b[:1]
    return DIGITS[digit_a] + _midpoint(a[1:] if a else "", None)


def key_between(a: str | None, b: str | None) -> str:
    """Return an order key strictly between ``a`` and ``b``.

    ``a is None`` means "before the first"; ``b is None`` means "after the last".
    ``key_between(None, None)`` seeds the first key. Raises ``ValueError`` if
    ``a >= b`` or either key is malformed.
    """
    if a is not None:
        _validate_order_key(a)
    if b is not None:
        _validate_order_key(b)
    if a is not None and b is not None and a >= b:
        raise ValueError(f"{a!r} >= {b!r}")

    if a is None:
        if b is None:
            return _INTEGER_ZERO
        ib = _integer_part(b)
        fb = b[len(ib) :]
        if ib == _SMALLEST_INTEGER:
            return ib + _midpoint("", fb)
        if ib < b:
            return ib
        res = _decrement_integer(ib)
        if res is None:
            raise ValueError("cannot decrement any further")
        return res

    if b is None:
        ia = _integer_part(a)
        fa = a[len(ia) :]
        inc = _increment_integer(ia)
        return ia + _midpoint(fa, None) if inc is None else inc

    ia = _integer_part(a)
    fa = a[len(ia) :]
    ib = _integer_part(b)
    fb = b[len(ib) :]
    if ia == ib:
        return ia + _midpoint(fa, fb)
    inc = _increment_integer(ia)
    if inc is None:
        raise ValueError("cannot increment any further")
    if inc < b:
        return inc
    return ia + _midpoint(fa, None)
