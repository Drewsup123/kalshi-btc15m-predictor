"""Frozen proposed exits. Precedence: target, trail, tape, book stop."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExitConfig:
    target_cents: int = 8
    trail_arm_cents: int = 5
    trail_giveback_cents: int = 3
    adverse_book_cents: int = 10
    adverse_prints: int = 5


@dataclass(frozen=True)
class ExitDecision:
    reason: str
    bid: Decimal | None = None


def choose_exit(
    side: str,
    entry_ask: Decimal,
    current_bid: Decimal,
    hold_high_bid: Decimal,
    opposite_known_prints: int,
    cfg: ExitConfig,
) -> ExitDecision:
    entry = Decimal(str(entry_ask))
    bid = Decimal(str(current_bid))
    high = max(Decimal(str(hold_high_bid)), bid)
    cent = Decimal("0.01")
    if bid >= entry + cfg.target_cents * cent:
        return ExitDecision("exit_target", bid)
    if high >= entry + cfg.trail_arm_cents * cent and (high - bid) >= cfg.trail_giveback_cents * cent:
        return ExitDecision("exit_trail", bid)
    if opposite_known_prints >= cfg.adverse_prints:
        return ExitDecision("exit_adverse_tape", bid)
    if bid <= entry - cfg.adverse_book_cents * cent:
        return ExitDecision("exit_adverse_book", bid)
    return ExitDecision("hold", bid)
