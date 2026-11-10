"""Score universe, dedup, 15-minute grid holes. No order paths."""

from __future__ import annotations

from datetime import timedelta

from kxbtc15m.clock import parse_utc


def _finite(value) -> bool:
    if value is None or value == "":
        return False
    try:
        return abs(float(value)) < float("inf")
    except (TypeError, ValueError):
        return False


def normalize_row(row: dict) -> dict:
    """Map public GET aliases onto the score-universe schema. Does not invent prints."""
    out = dict(row)
    ticker = str(out.get("ticker") or "")
    series = str(out.get("series_ticker") or "")
    if (ticker.startswith("KXBTC15M") or series == "KXBTC15M") and not out.get("strike_type"):
        out["strike_type"] = "greater_or_equal"
    status = str(out.get("status") or "").strip().lower()
    result = str(out.get("result") or "").strip().lower()
    if status == "settled" and result in {"yes", "no"}:
        out["status"] = "finalized"
    if not out.get("settlement_ts"):
        for key in ("settled_time", "result_ts"):
            if out.get(key):
                out["settlement_ts"] = out[key]
                break
    return out


def is_scoreable(row: dict) -> bool:
    row = normalize_row(row)
    result = str(row.get("result") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    strike = str(row.get("strike_type") or "").strip().lower()
    return (
        status == "finalized"
        and result in {"yes", "no"}
        and strike == "greater_or_equal"
        and _finite(row.get("floor_strike"))
        and _finite(row.get("expiration_value"))
    )


def score_universe(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    scored, excluded = [], []
    for row in rows:
        norm = normalize_row(row)
        (scored if is_scoreable(norm) else excluded).append(norm)
    scored.sort(key=lambda r: parse_utc(r["close_time"]))
    return scored, excluded


def dedup_by_ticker(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "")
        if ticker and ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


def grid_holes(scored: list[dict]) -> list[str]:
    if len(scored) < 2:
        return []
    closes = [parse_utc(r["close_time"]) for r in scored]
    first, last = min(closes), max(closes)
    have = {c.strftime("%Y-%m-%dT%H:%M:%SZ") for c in closes}
    holes = []
    t = first
    while t <= last:
        key = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        if key not in have:
            holes.append(key)
        t += timedelta(minutes=15)
    return holes


def official_yes(expiration_value, floor_strike) -> str:
    return "yes" if float(expiration_value) >= float(floor_strike) else "no"
