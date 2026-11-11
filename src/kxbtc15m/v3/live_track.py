"""Append-only live hero calls + scoring against settled Kalshi results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from kxbtc15m.clock import parse_utc
from kxbtc15m.v3.hero import format_correct_summary

LIVE_CALLS_NAME = "live_calls.jsonl"
DENVER = ZoneInfo("America/Denver")


def _key(call: dict) -> tuple[str, int]:
    return str(call.get("ticker") or ""), int(call.get("decision_offset_s") or 0)


def load_calls(state_dir: Path) -> list[dict]:
    path = Path(state_dir) / LIVE_CALLS_NAME
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def record_frozen_call(state_dir: Path, call: dict) -> bool:
    """Append once per (ticker, decision_offset_s). Never edits prior lines."""
    ticker = call.get("ticker")
    pred = str(call.get("pred_yes") or "").lower()
    if not ticker or pred not in {"yes", "no"}:
        return False
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    existing = load_calls(state_dir)
    key = _key(call)
    if any(_key(c) == key for c in existing):
        return False
    row = {
        "ticker": ticker,
        "pred_yes": pred,
        "decision_offset_s": int(call.get("decision_offset_s") or 0),
        "prediction_asof": call.get("prediction_asof"),
        "p_yes": call.get("p_yes"),
        "family": call.get("family"),
        "frozen_at": call.get("frozen_at") or call.get("observation_at"),
        "S_t": call.get("S_t"),
        "hero_direction": "UP" if pred == "yes" else "DOWN",
    }
    path = state_dir / LIVE_CALLS_NAME
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return True


def score_calls_against_settled(calls: list[dict], settled: list[dict]) -> list[dict]:
    """Join frozen calls to settled results. Does not mutate the on-disk log."""
    by_ticker: dict[str, dict] = {}
    for m in settled:
        t = m.get("ticker")
        if not t:
            continue
        result = str(m.get("result") or "").lower()
        if result not in {"yes", "no"}:
            continue
        by_ticker[str(t)] = m
    out: list[dict] = []
    for call in calls:
        item = dict(call)
        market = by_ticker.get(str(call.get("ticker") or ""))
        if not market:
            item["result"] = None
            item["correct"] = None
            item["settlement_ts"] = None
        else:
            result = str(market.get("result") or "").lower()
            item["result"] = result
            item["correct"] = str(call.get("pred_yes") or "").lower() == result
            item["settlement_ts"] = market.get("settlement_ts") or market.get("close_time")
        out.append(item)
    return out


def _denver_day(dt: datetime) -> str:
    return dt.astimezone(DENVER).strftime("%Y-%m-%d")


def _bucket_summary(rows: list[dict]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("correct") is not None]
    n = len(scored)
    k = sum(1 for r in scored if r.get("correct") is True)
    return {
        "n_scored": n,
        "n_correct": k,
        "n_pending": sum(1 for r in rows if r.get("correct") is None),
        "summary": format_correct_summary(k, n),
        "accuracy": (float(k) / float(n)) if n else None,
    }


def summarize_track(scored_calls: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today_key = _denver_day(now)
    today_rows = []
    for r in scored_calls:
        if r.get("correct") is None:
            continue
        ts = r.get("settlement_ts") or r.get("frozen_at") or r.get("prediction_asof")
        if not ts:
            continue
        try:
            day = _denver_day(parse_utc(ts))
        except Exception:
            continue
        if day == today_key:
            today_rows.append(r)
    return {
        "all_time": _bucket_summary(scored_calls),
        "today": _bucket_summary(today_rows),
        "asof_denver_day": today_key,
    }


def recent_scored(scored_calls: list[dict], limit: int = 15) -> list[dict]:
    done = [r for r in scored_calls if r.get("correct") is not None]
    done.sort(key=lambda r: str(r.get("settlement_ts") or r.get("prediction_asof") or ""))
    return done[-limit:]


def attach_live_track(state_dir: Path, settled_markets: list[dict], now: datetime | None = None) -> dict:
    calls = load_calls(state_dir)
    scored = score_calls_against_settled(calls, settled_markets)
    summary = summarize_track(scored, now=now)
    recent = recent_scored(scored, limit=15)
    payload = {
        "summary": summary,
        "recent": recent,
        "n_calls_recorded": len(calls),
    }
    (Path(state_dir) / "live_track.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return payload
