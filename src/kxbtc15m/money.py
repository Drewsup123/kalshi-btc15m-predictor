"""Integer-cent helpers. Contract prices may be fractional cents; costs ceil."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

CENT = Decimal("0.01")


def _as_decimal(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def dollars_to_cents_ceil(value: Decimal | int | float | str) -> int:
    dollars = _as_decimal(value)
    if dollars < 0:
        raise ValueError("money must be non-negative")
    cents = (dollars / CENT).to_integral_value(rounding=ROUND_CEILING)
    return int(cents)


def cents_to_dollars(cents: int) -> str:
    if cents < 0:
        raise ValueError("money must be non-negative")
    return f"{Decimal(cents) / Decimal(100):.2f}"
