"""Coinbase 1m bars. Period end = start+60s. Event time is not a receipt."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kxbtc15m.clock import parse_utc


def period_end(start: datetime) -> datetime:
    return start + timedelta(seconds=60)


def parse_exchange_row(row: list) -> dict:
    start = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
    return {
        "start": start,
        "low": float(row[1]),
        "high": float(row[2]),
        "open": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
    }


def filter_completed(bars: list[dict], t_star: datetime | str) -> list[dict]:
    cutoff = parse_utc(t_star)
    kept = []
    for bar in bars:
        start = bar["start"] if isinstance(bar["start"], datetime) else parse_utc(bar["start"])
        if period_end(start) <= cutoff:
            item = dict(bar)
            item["start"] = start
            kept.append(item)
    kept.sort(key=lambda b: b["start"])
    return kept


def last_close(bars: list[dict], t_star: datetime | str) -> tuple[float | None, datetime | None]:
    done = filter_completed(bars, t_star)
    if not done:
        return None, None
    bar = done[-1]
    return float(bar["close"]), period_end(bar["start"])
