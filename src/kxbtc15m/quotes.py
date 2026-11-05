"""Conservative executable quotes and skip reasons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from kxbtc15m.clock import parse_utc

OPEN_STATUSES = frozenset({"active", "open"})


@dataclass(frozen=True)
class QuoteConfig:
    stale_seconds: int = 30
    near_close_seconds: int = 60
    ask_epsilon: Decimal = Decimal("0.02")


@dataclass(frozen=True)
class QuoteDecision:
    ok: bool
    skip_reason: str | None
    yes_ask: Decimal | None = None
    no_ask: Decimal | None = None
    yes_size: Decimal | None = None
    no_size: Decimal | None = None
    market_ticker: str | None = None
    close_time: str | None = None


def _dec(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    if not parsed.is_finite():
        return None
    return parsed


def _levels(book: dict, side: str) -> list[tuple[Decimal, Decimal]]:
    fp = (book or {}).get("orderbook_fp") or {}
    raw = fp.get(f"{side}_dollars") or []
    levels: list[tuple[Decimal, Decimal]] = []
    for row in raw:
        if not row or len(row) < 2:
            continue
        price = _dec(row[0])
        size = _dec(row[1])
        if price is None or size is None or price <= 0 or size < 0:
            continue
        levels.append((price, size))
    return levels


def _best_bid(levels: list[tuple[Decimal, Decimal]]) -> tuple[Decimal, Decimal] | None:
    if not levels:
        return None
    return max(levels, key=lambda item: item[0])


def evaluate_quote(
    market: dict,
    book: dict,
    now: datetime,
    snapshot_at: datetime,
    cfg: QuoteConfig,
) -> QuoteDecision:
    ticker = market.get("ticker")
    close_time = market.get("close_time")
    status = str(market.get("status") or "").lower()
    if status not in OPEN_STATUSES:
        return QuoteDecision(False, "market_not_open", market_ticker=ticker, close_time=close_time)

    age = (parse_utc(now) - parse_utc(snapshot_at)).total_seconds()
    if age > cfg.stale_seconds:
        return QuoteDecision(False, "stale_quote", market_ticker=ticker, close_time=close_time)

    if close_time:
        seconds_to_close = (parse_utc(close_time) - parse_utc(now)).total_seconds()
        if seconds_to_close < cfg.near_close_seconds:
            return QuoteDecision(False, "near_close", market_ticker=ticker, close_time=close_time)

    yes_levels = _levels(book, "yes")
    no_levels = _levels(book, "no")
    best_yes = _best_bid(yes_levels)
    best_no = _best_bid(no_levels)
    if best_yes is None or best_no is None:
        return QuoteDecision(False, "thin_book", market_ticker=ticker, close_time=close_time)

    market_yes_ask = _dec(market.get("yes_ask_dollars"))
    market_no_ask = _dec(market.get("no_ask_dollars"))
    if market_yes_ask is None or market_no_ask is None:
        return QuoteDecision(False, "invalid_quote", market_ticker=ticker, close_time=close_time)
    if market_yes_ask <= 0 or market_yes_ask >= 1 or market_no_ask <= 0 or market_no_ask >= 1:
        return QuoteDecision(False, "invalid_ask", market_ticker=ticker, close_time=close_time)

    implied_yes_ask = Decimal("1") - best_no[0]
    implied_no_ask = Decimal("1") - best_yes[0]
    if (abs(market_yes_ask - implied_yes_ask) > cfg.ask_epsilon) or (
        abs(market_no_ask - implied_no_ask) > cfg.ask_epsilon
    ):
        return QuoteDecision(False, "inconsistent_book", market_ticker=ticker, close_time=close_time)

    yes_ask = max(market_yes_ask, implied_yes_ask)
    no_ask = max(market_no_ask, implied_no_ask)
    if yes_ask <= 0 or yes_ask >= 1 or no_ask <= 0 or no_ask >= 1:
        return QuoteDecision(False, "invalid_ask", market_ticker=ticker, close_time=close_time)

    return QuoteDecision(
        True,
        None,
        yes_ask=yes_ask,
        no_ask=no_ask,
        yes_size=best_no[1],
        no_size=best_yes[1],
        market_ticker=ticker,
        close_time=close_time,
    )


def ask_and_size(decision: QuoteDecision, side: str) -> tuple[Decimal, Decimal]:
    if side == "yes":
        if decision.yes_ask is None or decision.yes_size is None:
            raise ValueError("yes quote missing")
        return decision.yes_ask, decision.yes_size
    if side == "no":
        if decision.no_ask is None or decision.no_size is None:
            raise ValueError("no quote missing")
        return decision.no_ask, decision.no_size
    raise ValueError(f"unknown side {side}")
