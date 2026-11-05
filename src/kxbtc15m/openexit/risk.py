"""Size so entry debit + reserved exit fee stays <= $1 inclusive."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kxbtc15m.fees import taker_fee_cents
from kxbtc15m.money import dollars_to_cents_ceil


@dataclass(frozen=True)
class OpenExitRisk:
    max_debit_cents: int = 100
    max_daily_downside_cents: int = 500
    max_pending: int = 1


@dataclass(frozen=True)
class SizeDecision:
    ok: bool
    skip_reason: str | None
    contracts: int = 0
    ask: Decimal | None = None
    cost_cents: int = 0
    entry_fee_cents: int = 0
    exit_fee_reserve_cents: int = 0
    entry_debit_cents: int = 0
    reserve_cents: int = 0
    full_intended: bool = True


def size_entry(
    ask: Decimal,
    book_size: Decimal,
    cash_cents: int,
    used_downside_cents: int,
    pending_count: int,
    cfg: OpenExitRisk,
) -> SizeDecision:
    if pending_count >= cfg.max_pending:
        return SizeDecision(False, "pending_open")
    max_from_book = int(Decimal(str(book_size)))
    if max_from_book < 1:
        return SizeDecision(False, "thin_book")
    first = None
    best = None
    intended = None
    for contracts in range(1, max_from_book + 1):
        try:
            entry_fee = taker_fee_cents(contracts, ask)
            exit_reserve = taker_fee_cents(contracts, Decimal("0.50"))
            cost = dollars_to_cents_ceil(Decimal(str(ask)) * contracts)
        except ValueError:
            first = first or "invalid_ask"
            break
        entry_debit = cost + entry_fee
        reserve = entry_debit + exit_reserve
        if intended is None:
            intended = contracts
        if reserve > cfg.max_debit_cents:
            first = first or "per_pick_cap"
            break
        if reserve > cash_cents:
            first = first or "insufficient_cash"
            break
        if used_downside_cents + reserve > cfg.max_daily_downside_cents:
            first = first or "daily_downside_cap"
            break
        best = SizeDecision(
            True,
            None,
            contracts=contracts,
            ask=Decimal(str(ask)),
            cost_cents=cost,
            entry_fee_cents=entry_fee,
            exit_fee_reserve_cents=exit_reserve,
            entry_debit_cents=entry_debit,
            reserve_cents=reserve,
            full_intended=True,
        )
    if best is None:
        return SizeDecision(False, first or "per_pick_cap")
    if intended is not None:
        best = SizeDecision(**{**best.__dict__, "full_intended": best.contracts == max_from_book or True})
    return best
