"""Point-in-time YES price from public trades. Not settled-row last_price."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from kxbtc15m.clock import parse_utc
from kxbtc15m.v3.client import FeedError, PublicGetClient
from kxbtc15m.v3.fetch import DEFAULT_API_BASE


def last_yes_asof(trades: list[dict], t_dec: datetime) -> float | None:
    eligible = []
    for trade in trades:
        created = trade.get("created_time")
        if not created:
            continue
        if parse_utc(created) > t_dec:
            continue
        price = trade.get("yes_price_dollars")
        if price in (None, ""):
            continue
        try:
            eligible.append((parse_utc(created), float(price)))
        except (TypeError, ValueError):
            continue
    if not eligible:
        return None
    eligible.sort(key=lambda x: x[0])
    return eligible[-1][1]


def load_cached_trades(cache_dir: Path, ticker: str) -> list[dict] | None:
    path = cache_dir / "raw" / "trades" / f"{ticker}.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        trades = payload.get("trades")
        return trades if isinstance(trades, list) else []
    return []


def fetch_ticker_trades(
    client: PublicGetClient,
    ticker: str,
    cache_dir: Path,
    api_base: str = DEFAULT_API_BASE,
) -> list[dict]:
    cached = load_cached_trades(cache_dir, ticker)
    if cached is not None:
        return cached
    trades: list[dict] = []
    for path in (f"/markets/trades", f"/historical/trades"):
        try:
            payload = client.kalshi(api_base, path, {"ticker": ticker, "limit": "200"})
        except FeedError as exc:
            if exc.status == 404:
                continue
            raise
        batch = payload.get("trades") if isinstance(payload, dict) else None
        if isinstance(batch, list):
            trades.extend(batch)
            break
    out_dir = cache_dir / "raw" / "trades"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{ticker}.json").write_text(json.dumps({"trades": trades}) + "\n", encoding="utf-8")
    return trades
