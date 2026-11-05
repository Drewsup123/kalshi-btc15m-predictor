"""Last-10 official finalized majority. Not sentiment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kxbtc15m.clock import parse_utc


@dataclass(frozen=True)
class Lean:
    side: str | None
    skip_reason: str | None
    yes_count: int
    no_count: int
    used: int
    tickers: tuple[str, ...]


def choose_lean(markets: list[dict], open_time: datetime | str) -> Lean:
    open_dt = parse_utc(open_time)
    eligible: list[dict] = []
    for market in markets:
        result = str(market.get("result") or "").strip().lower()
        if result not in {"yes", "no"}:
            continue
        close = market.get("close_time")
        if not close:
            continue
        if parse_utc(close) >= open_dt:
            continue
        eligible.append(market)
    eligible.sort(key=lambda row: parse_utc(row["close_time"]), reverse=True)
    window = eligible[:10]
    yes_count = sum(1 for row in window if str(row["result"]).lower() == "yes")
    no_count = sum(1 for row in window if str(row["result"]).lower() == "no")
    used = len(window)
    tickers = tuple(str(row.get("ticker") or "") for row in window)
    if used < 10:
        return Lean(None, "insufficient_history", yes_count, no_count, used, tickers)
    if yes_count == no_count:
        return Lean(None, "lean_tie", yes_count, no_count, used, tickers)
    side = "yes" if yes_count > no_count else "no"
    return Lean(side, None, yes_count, no_count, used, tickers)
