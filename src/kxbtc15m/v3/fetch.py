"""Page public Kalshi settled markets and Coinbase 1m candles. GET only."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kxbtc15m.schema import unwrap_markets
from kxbtc15m.v3.candles import parse_exchange_row
from kxbtc15m.v3.client import FeedError, PublicGetClient
from kxbtc15m.v3.inventory import dedup_by_ticker, grid_holes, score_universe

DEFAULT_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
COINBASE = "https://api.exchange.coinbase.com"


def _save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def fetch_kalshi_settled(
    client: PublicGetClient,
    cache_dir: Path,
    api_base: str = DEFAULT_API_BASE,
    series: str = "KXBTC15M",
) -> list[dict]:
    rows: list[dict] = []
    for kind, path in (
        ("live", "/markets"),
        ("historical", "/historical/markets"),
    ):
        cursor = None
        page = 0
        while True:
            query = {"series_ticker": series, "limit": "200"}
            if kind == "live":
                query["status"] = "settled"
            if cursor:
                query["cursor"] = cursor
            try:
                payload = client.kalshi(api_base, path, query)
            except FeedError as exc:
                if exc.status == 404:
                    _save(cache_dir / "raw" / f"{kind}-missing.json", {"error": str(exc), "path": path})
                    break
                raise
            _save(cache_dir / "raw" / f"{kind}-{page:04d}.json", payload)
            batch = unwrap_markets(payload)
            rows.extend(batch)
            next_cursor = payload.get("cursor") or None
            page += 1
            if not next_cursor or not batch or next_cursor == cursor:
                break
            cursor = next_cursor
            time.sleep(0.2)
    return dedup_by_ticker(rows)


def fetch_coinbase_1m(
    client: PublicGetClient,
    start: datetime,
    end: datetime,
    cache_dir: Path,
) -> list[dict]:
    bars: list[dict] = []
    cursor = start
    chunk = timedelta(minutes=300)
    idx = 0
    while cursor < end:
        chunk_end = min(cursor + chunk, end)
        url = (
            f"{COINBASE}/products/BTC-USD/candles"
            f"?granularity=60&start={int(cursor.timestamp())}"
            f"&end={int(chunk_end.timestamp())}"
        )
        payload = client.get_json(url)
        _save(cache_dir / "raw" / f"cb-{idx:05d}.json", payload)
        if isinstance(payload, list):
            for row in payload:
                try:
                    bars.append(parse_exchange_row(row))
                except (TypeError, ValueError, IndexError):
                    continue
        idx += 1
        cursor = chunk_end
        time.sleep(0.25)
    uniq = {int(b["start"].timestamp()): b for b in bars}
    return [uniq[k] for k in sorted(uniq)]


def inventory_report(raw_markets: list[dict], dataset_asof: str) -> dict:
    scored, excluded = score_universe(raw_markets)
    holes = grid_holes(scored)
    yes = sum(1 for r in scored if str(r.get("result")).lower() == "yes")
    return {
        "dataset_asof": dataset_asof,
        "n_raw": len(raw_markets),
        "n_score_universe": len(scored),
        "n_excluded": len(excluded),
        "n_grid_holes": len(holes),
        "grid_holes_head": holes[:50],
        "yes": yes,
        "no": len(scored) - yes,
        "first_close": scored[0]["close_time"] if scored else None,
        "last_close": scored[-1]["close_time"] if scored else None,
        "availability": "historical_replay",
        "replay_assumption": "prior_print_after_settlement_ts",
    }
