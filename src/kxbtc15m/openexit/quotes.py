"""Book-complement executable quotes. Small ask/book disagreement does not skip."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from kxbtc15m.clock import parse_utc
from kxbtc15m.quotes import _best_bid, _dec, _levels

OPEN_STATUSES = frozenset({"active", "open"})


@dataclass(frozen=True)
class LiveQuoteConfig:
    stale_seconds: int = 30
    near_close_seconds: int = 60


@dataclass(frozen=True)
class LiveQuotes:
    ok: bool
    skip_reason: str | None
    yes_ask: Decimal | None = None
    no_ask: Decimal | None = None
    yes_bid: Decimal | None = None
    no_bid: Decimal | None = None
    yes_ask_size: Decimal | None = None
    no_ask_size: Decimal | None = None
    yes_bid_size: Decimal | None = None
    no_bid_size: Decimal | None = None


def _valid_px(value: Decimal | None) -> bool:
    return value is not None and value > 0 and value < 1


def live_quotes(
    market: dict,
    book: dict,
    now: datetime,
    snapshot_at: datetime,
    cfg: LiveQuoteConfig,
) -> LiveQuotes:
    status = str(market.get("status") or "").lower()
    if status not in OPEN_STATUSES:
        return LiveQuotes(False, "market_not_open")
    if (parse_utc(now) - parse_utc(snapshot_at)).total_seconds() > cfg.stale_seconds:
        return LiveQuotes(False, "stale_quote")
    close = market.get("close_time")
    if close and (parse_utc(close) - parse_utc(now)).total_seconds() < cfg.near_close_seconds:
        return LiveQuotes(False, "near_close")

    best_yes = _best_bid(_levels(book, "yes"))
    best_no = _best_bid(_levels(book, "no"))
    if best_yes is None or best_no is None:
        return LiveQuotes(False, "thin_book")

    implied_yes_ask = Decimal("1") - best_no[0]
    implied_no_ask = Decimal("1") - best_yes[0]
    market_yes_ask = _dec(market.get("yes_ask_dollars"))
    market_no_ask = _dec(market.get("no_ask_dollars"))
    market_yes_bid = _dec(market.get("yes_bid_dollars"))
    market_no_bid = _dec(market.get("no_bid_dollars"))

    yes_ask = implied_yes_ask
    if _valid_px(market_yes_ask):
        yes_ask = max(market_yes_ask, implied_yes_ask) if _valid_px(implied_yes_ask) else market_yes_ask
    no_ask = implied_no_ask
    if _valid_px(market_no_ask):
        no_ask = max(market_no_ask, implied_no_ask) if _valid_px(implied_no_ask) else market_no_ask

    yes_bid = best_yes[0]
    if _valid_px(market_yes_bid):
        yes_bid = min(market_yes_bid, best_yes[0])
    no_bid = best_no[0]
    if _valid_px(market_no_bid):
        no_bid = min(market_no_bid, best_no[0])

    if not (_valid_px(yes_ask) and _valid_px(no_ask) and _valid_px(yes_bid) and _valid_px(no_bid)):
        return LiveQuotes(False, "invalid_quote")

    return LiveQuotes(
        True,
        None,
        yes_ask=yes_ask,
        no_ask=no_ask,
        yes_bid=yes_bid,
        no_bid=no_bid,
        yes_ask_size=best_no[1],
        no_ask_size=best_yes[1],
        yes_bid_size=best_yes[1],
        no_bid_size=best_no[1],
    )


def side_ask_bid(quotes: LiveQuotes, side: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if side == "yes":
        return quotes.yes_ask, quotes.yes_bid, quotes.yes_ask_size, quotes.yes_bid_size
    if side == "no":
        return quotes.no_ask, quotes.no_bid, quotes.no_ask_size, quotes.no_bid_size
    raise ValueError(side)
