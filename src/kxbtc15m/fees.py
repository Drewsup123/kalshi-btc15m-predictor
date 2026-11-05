"""Official Kalshi quadratic taker fee. Fail closed if the excerpt is missing."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from kxbtc15m.money import dollars_to_cents_ceil

FEE_CONSTANT = Decimal("0.07")

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_EXCERPT_PATH = _PACKAGE_ROOT / "docs" / "official" / "kalshi-fee-schedule-excerpt.md"

_REQUIRED_MARKERS = ("0.07", "round up", "M", "C", "P")


def load_official_excerpt(path: Path | str | None = None) -> str:
    excerpt = Path(path) if path is not None else OFFICIAL_EXCERPT_PATH
    if not excerpt.is_file():
        raise ValueError(f"official fee excerpt missing; fail closed: {excerpt}")
    return excerpt.read_text(encoding="utf-8")


def assert_fee_source_ok(excerpt_text: str) -> None:
    lowered = excerpt_text.lower()
    missing = [marker for marker in _REQUIRED_MARKERS if marker.lower() not in lowered]
    if missing:
        raise ValueError(
            "official fee excerpt does not contain required formula markers; "
            f"fail closed (missing {missing})"
        )
    if "0.07" not in excerpt_text:
        raise ValueError("official fee excerpt missing 0.07 constant; fail closed")


def taker_fee_cents(
    contracts: int,
    price_dollars: Decimal | str | float,
    multiplier: Decimal | str | float | int = 1,
    fee_constant: Decimal | None = None,
) -> int:
    if contracts <= 0:
        raise ValueError("contracts must be >= 1")
    price = Decimal(str(price_dollars))
    if price <= 0 or price >= 1:
        raise ValueError("price must be in (0, 1)")
    constant = FEE_CONSTANT if fee_constant is None else Decimal(str(fee_constant))
    if constant != FEE_CONSTANT:
        raise ValueError("refusing non-official fee constant; fail closed")
    raw = constant * Decimal(str(multiplier)) * Decimal(contracts) * price * (Decimal(1) - price)
    return dollars_to_cents_ceil(raw)
