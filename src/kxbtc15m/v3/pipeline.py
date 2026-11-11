"""Inventory → candles → evaluate → screen. Isolated V3 dir only."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kxbtc15m.clock import parse_utc
from kxbtc15m.v3.candles import parse_exchange_row
from kxbtc15m.v3.client import PublicGetClient
from kxbtc15m.v3.evaluate import build_replay_rows, evaluate_rows
from kxbtc15m.v3.lock import read_lock
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


def run_sweep_cached(state_dir: Path) -> dict:
    from kxbtc15m.v3.sweep import run_sweep

    state_dir = assert_safe_v3_dir(state_dir)
    markets = json.loads((state_dir / "markets.json").read_text(encoding="utf-8"))
    bars = _load_bars(state_dir)
    inv = {}
    if (state_dir / "inventory.json").is_file():
        inv = json.loads((state_dir / "inventory.json").read_text(encoding="utf-8"))
    dataset_asof = inv.get("dataset_asof") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lock_asof = dataset_asof
    lock_path = state_dir / "lock.json"
    if lock_path.is_file():
        lock_asof = read_lock(lock_path).get("dataset_asof") or dataset_asof
    return run_sweep(markets, bars, state_dir, dataset_asof, lock_dataset_asof=lock_asof)


def _sample_implied_trades(state_dir: Path, markets: list[dict], api_base: str, every: int = 25) -> int:
    from kxbtc15m.v3.client import PublicGetClient
    from kxbtc15m.v3.implied import fetch_ticker_trades

    client = PublicGetClient()
    n = 0
    for i, market in enumerate(markets):
        if i % every != 0:
            continue
        ticker = market.get("ticker")
        if not ticker:
            continue
        try:
            fetch_ticker_trades(client, ticker, state_dir, api_base=api_base)
            n += 1
        except Exception:
            continue
    return n


def run_preview(state_dir: Path, api_base: str) -> dict:
    from kxbtc15m.v3.client import PublicGetClient
    from kxbtc15m.v3.fetch import fetch_coinbase_1m
    from kxbtc15m.v3.inventory import score_universe
    from kxbtc15m.v3.preview import build_preview_bundle
    from kxbtc15m.v3.split import chronological_split as _cs
    from kxbtc15m.v3.sweep import PREOPEN_OFFSET, _fit_models

    state_dir = assert_safe_v3_dir(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    markets = json.loads((state_dir / "markets.json").read_text(encoding="utf-8"))
    bars = _load_bars(state_dir)
    client = PublicGetClient()
    now = datetime.now(timezone.utc)
    recent = fetch_coinbase_1m(client, now - timedelta(hours=6), now + timedelta(minutes=1), state_dir)
    by_ts = {int(b["start"].timestamp()): b for b in bars}
    for b in recent:
        by_ts[int(b["start"].timestamp())] = b
    bars = [by_ts[k] for k in sorted(by_ts)]
    live_settled = client.kalshi(api_base, "/markets", {"series_ticker": "KXBTC15M", "status": "settled", "limit": "50"})
    extra, _ = score_universe(live_settled.get("markets") or [])
    seen = {m.get("ticker") for m in markets}
    for row in extra:
        if row.get("ticker") not in seen:
            markets.append(row)
            seen.add(row.get("ticker"))
    rows0 = build_replay_rows(markets, bars, offset_seconds=PREOPEN_OFFSET)
    train, _val, _ho = _cs(rows0)
    fit0 = _fit_models(train)
    rows30 = build_replay_rows(markets, bars, offset_seconds=30)
    train30, _, _ = _cs(rows30)
    fit30 = _fit_models(train30)
    family_pre = "A_logistic_z"
    family_win = "D_brownian_16"
    sel_path = state_dir / "sweep" / "selection.json"
    if sel_path.is_file():
        sel = json.loads(sel_path.read_text(encoding="utf-8"))
        chosen = (sel.get("selection") or {}).get("chosen") or {}
        fam = chosen.get("family") or chosen.get("id") or ""
        if isinstance(fam, str) and fam.startswith("S_"):
            fam = fam.split("_")[1] if "_" in fam else "D_brownian_16"
        if chosen.get("offset_s") == 0:
            family_pre = chosen.get("family") or family_pre
        if chosen.get("family") in {"D_brownian_16", "D_brownian_96", "C_lastprice", "A_logistic", "A_logistic_z", "E_regime_trend", "F_vote"}:
            family_win = chosen.get("family")
        elif "brownian" in str(fam):
            family_win = "D_brownian_16"
    bundle = build_preview_bundle(
        client,
        bars,
        markets,
        fit0,
        fit30,
        family_pre,
        family_win,
        api_base=api_base,
    )
    sweep_holdout = []
    summary_path = state_dir / "sweep" / "summary.json"
    if summary_path.is_file():
        try:
            sweep_holdout = json.loads(summary_path.read_text(encoding="utf-8")).get("holdout") or []
        except json.JSONDecodeError:
            sweep_holdout = []
    from kxbtc15m.v3.hero import enrich_hero_card
    from kxbtc15m.v3.live_track import attach_live_track, record_frozen_call

    if bundle.get("current"):
        bundle["current"] = enrich_hero_card(bundle["current"], sweep_holdout)
    if bundle.get("next"):
        bundle["next"] = enrich_hero_card(bundle["next"], sweep_holdout)
    bundle["run_generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bundle["stale"] = False
    # Freeze live call when we have a classifier side (append-once).
    cur = bundle.get("current") or {}
    if cur.get("ticker") and cur.get("pred_yes") in {"yes", "no"}:
        record_frozen_call(
            state_dir,
            {
                "ticker": cur.get("ticker"),
                "pred_yes": cur.get("pred_yes"),
                "decision_offset_s": cur.get("decision_offset_s"),
                "prediction_asof": cur.get("prediction_asof"),
                "p_yes": cur.get("p_yes"),
                "family": cur.get("family"),
                "frozen_at": bundle["run_generated_at"],
                "S_t": cur.get("S_t"),
            },
        )
    bundle["live_track"] = attach_live_track(state_dir, markets, now=now)
    (state_dir / "preview.json").write_text(json.dumps(bundle, indent=2, default=str) + "\n", encoding="utf-8")
    write_screen(state_dir)
    return bundle
