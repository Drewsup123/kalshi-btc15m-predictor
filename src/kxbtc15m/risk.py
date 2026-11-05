"""Paper risk: $1 inclusive debit, $5 pending-aware daily downside, one pending."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kxbtc15m.fees import taker_fee_cents
from kxbtc15m.money import dollars_to_cents_ceil


@dataclass(frozen=True)
class RiskConfig:
    starting_cash_cents: int = 10000
    max_debit_cents: int = 100
    max_daily_downside_cents: int = 500
    max_pending: int = 1


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    skip_reason: str | None
    contracts: int = 0
    ask: Decimal | None = None
    cost_cents: int = 0
    fee_cents: int = 0
    debit_cents: int = 0


def _quote_cost(ask: Decimal, contracts: int) -> tuple[int, int, int]:
    fee_cents = taker_fee_cents(contracts, ask)
    cost_cents = dollars_to_cents_ceil(ask * Decimal(contracts))
    return cost_cents, fee_cents, cost_cents + fee_cents


def size_and_gate(
    ask: Decimal,
    book_size: Decimal,
    cash_cents: int,
    used_downside_cents: int,
    pending_count: int,
    cfg: RiskConfig,
) -> RiskDecision:
    if pending_count >= cfg.max_pending:
        return RiskDecision(False, "pending_open")
    max_from_book = int(Decimal(str(book_size)))
    if max_from_book < 1:
        return RiskDecision(False, "thin_book")

    first_failure: str | None = None
    best: RiskDecision | None = None
    for contracts in range(1, max_from_book + 1):
        try:
            cost_cents, fee_cents, debit_cents = _quote_cost(Decimal(str(ask)), contracts)
        except ValueError:
            first_failure = first_failure or "invalid_ask"
            break
        if debit_cents > cfg.max_debit_cents:
            first_failure = first_failure or "per_pick_cap"
            break
        if debit_cents > cash_cents:
            first_failure = first_failure or "insufficient_cash"
            break
        if used_downside_cents + debit_cents > cfg.max_daily_downside_cents:
            first_failure = first_failure or "daily_downside_cap"
            break
        best = RiskDecision(
            True,
            None,
            contracts=contracts,
            ask=Decimal(str(ask)),
            cost_cents=cost_cents,
            fee_cents=fee_cents,
            debit_cents=debit_cents,
        )
    if best is not None:
        return best
    return RiskDecision(False, first_failure or "per_pick_cap")
