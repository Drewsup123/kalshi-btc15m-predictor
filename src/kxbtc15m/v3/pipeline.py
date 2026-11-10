"""Inventory → candles → evaluate → screen. Isolated V3 dir only."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kxbtc15m.clock import parse_utc
from kxbtc15m.v3.candles import parse_exchange_row
from kxbtc15m.v3.client import PublicGetClient
from kxbtc15m.v3.evaluate import build_replay_rows, evaluate_rows
from kxbtc15m.v3.fetch import (
    DEFAULT_API_BASE,
    fetch_coinbase_1m,
    fetch_kalshi_settled,
    inventory_report,
)
from kxbtc15m.v3.inventory import score_universe
from kxbtc15m.v3.paths import assert_safe_v3_dir
from kxbtc15m.v3.screen import write_screen


def run_inventory(state_dir: Path, api_base: str = DEFAULT_API_BASE) -> dict:
    state_dir = assert_safe_v3_dir(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    client = PublicGetClient()
    raw = fetch_kalshi_settled(client, state_dir, api_base=api_base)
    scored, _excluded = score_universe(raw)
    dataset_asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = inventory_report(raw, dataset_asof)
    (state_dir / "markets.json").write_text(json.dumps(scored, default=str) + "\n", encoding="utf-8")
    (state_dir / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if scored:
        start = parse_utc(scored[0]["open_time"]) - timedelta(hours=4)
        end = parse_utc(scored[-1]["close_time"]) + timedelta(minutes=2)
        bars = fetch_coinbase_1m(client, start, end, state_dir)
        serial = [
            {
                "start": b["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b["volume"],
            }
            for b in bars
        ]
        (state_dir / "candles.json").write_text(json.dumps(serial) + "\n", encoding="utf-8")
        report["n_candles"] = len(serial)
        (state_dir / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _load_bars(state_dir: Path) -> list[dict]:
    raw = json.loads((state_dir / "candles.json").read_text(encoding="utf-8"))
    bars = []
    for row in raw:
        if isinstance(row, list):
            bars.append(parse_exchange_row(row))
        else:
            bars.append(
                {
                    "start": parse_utc(row["start"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
    return bars


def run_evaluate_cached(state_dir: Path) -> dict:
    state_dir = assert_safe_v3_dir(state_dir)
    markets = json.loads((state_dir / "markets.json").read_text(encoding="utf-8"))
    bars = _load_bars(state_dir)
    inv = {}
    if (state_dir / "inventory.json").is_file():
        inv = json.loads((state_dir / "inventory.json").read_text(encoding="utf-8"))
    dataset_asof = inv.get("dataset_asof") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = build_replay_rows(markets, bars)
    return evaluate_rows(rows, state_dir, dataset_asof)


def run_screen(state_dir: Path) -> Path:
    state_dir = assert_safe_v3_dir(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    return write_screen(state_dir)
