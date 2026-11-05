"""Experimental versioned baseline: momentum with deterministic seeded fallback."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

MODEL_VERSION = "exp-baseline-v1@2026-11-05"
ENTRY_CLASS = "experimental"
DEFAULT_SEED = 20261105
DEFAULT_THRESHOLD = Decimal("20")


@dataclass(frozen=True)
class LastPrint:
    floor: Decimal
    expiration: Decimal


@dataclass(frozen=True)
class Signal:
    side: str
    rule: str
    model_version: str
    entry_class: str
    inputs_hash: str
    p_hat: None
    skip_reason: str | None = None


def _seeded_side(market_ticker: str, seed: int) -> str:
    digest = sha256(f"{seed}:{market_ticker}".encode("utf-8")).digest()
    return "yes" if digest[-1] % 2 == 0 else "no"


def choose_side(
    market_ticker: str,
    last_print: LastPrint | None,
    seed: int = DEFAULT_SEED,
    threshold_dollars: Decimal | int | str = DEFAULT_THRESHOLD,
    model_version: str = MODEL_VERSION,
) -> Signal:
    threshold = Decimal(str(threshold_dollars))
    rule = "seeded_control"
    side = _seeded_side(market_ticker, seed)
    move: Decimal | None = None
    if last_print is not None:
        move = last_print.expiration - last_print.floor
        if move >= threshold:
            side = "yes"
            rule = "momentum"
        elif move <= -threshold:
            side = "no"
            rule = "momentum"
    payload = (
        f"{model_version}|{rule}|{seed}|{market_ticker}|{side}|"
        f"{'' if last_print is None else f'{last_print.floor}:{last_print.expiration}'}"
        f"|{move if move is not None else ''}|"
    )
    return Signal(
        side=side,
        rule=rule,
        model_version=model_version,
        entry_class=ENTRY_CLASS,
        inputs_hash=sha256(payload.encode("utf-8")).hexdigest(),
        p_hat=None,
    )
