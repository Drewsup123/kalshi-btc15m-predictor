"""As-of opening ref and last-10. Event timestamps are not live receipts."""

from __future__ import annotations

from datetime import datetime
from math import log

from kxbtc15m.clock import parse_utc
from kxbtc15m.v3.clock import t_star as compute_t_star


def _eligible_prior(market: dict, t_star: datetime, availability: str) -> bool:
    result = str(market.get("result") or "").strip().lower()
    if result not in {"yes", "no"}:
        return False
    if not market.get("settlement_ts"):
        return False
    if availability == "historical_replay":
        return parse_utc(market["settlement_ts"]) <= t_star
    raise ValueError("observed_live eligibility needs observation_at")


def opening_ref(
    current: dict,
    priors: list[dict],
    t_star: datetime,
    availability: str = "historical_replay",
    observation_at: datetime | None = None,
    request_started_at: datetime | None = None,
) -> tuple[float | None, str | None, str | None]:
    """Return (S_t, source, skip_reason). Never uses eventual current floor on default path."""
    if availability == "observed_live":
        if observation_at is None or observation_at > t_star:
            return None, None, "insufficient_opening_ref"
    eligible = []
    for m in priors:
        if availability == "observed_live":
            if observation_at is None or observation_at > t_star:
                continue
            if not m.get("settlement_ts"):
                continue
            if parse_utc(m["settlement_ts"]) > t_star:
                continue
            result = str(m.get("result") or "").strip().lower()
            if result not in {"yes", "no"}:
                continue
            eligible.append(m)
        else:
            if _eligible_prior(m, t_star, availability):
                eligible.append(m)
    eligible.sort(key=lambda r: parse_utc(r["settlement_ts"]), reverse=True)
    if not eligible:
        return None, None, "insufficient_opening_ref"
    prior = eligible[0]
    try:
        value = float(prior["expiration_value"])
    except (TypeError, ValueError, KeyError):
        return None, None, "insufficient_opening_ref"
    return value, "prior_expiration_value", None


def last10(
    priors: list[dict],
    t_star: datetime,
    availability: str = "historical_replay",
    observation_at: datetime | None = None,
) -> dict:
    eligible = []
    for m in priors:
        if availability == "observed_live":
            if observation_at is None or observation_at > t_star:
                continue
        result = str(m.get("result") or "").strip().lower()
        if result not in {"yes", "no"}:
            continue
        if not m.get("settlement_ts"):
            continue
        if parse_utc(m["settlement_ts"]) > t_star:
            continue
        if not m.get("expiration_value") or m.get("floor_strike") in (None, ""):
            continue
        eligible.append(m)
    eligible.sort(key=lambda r: parse_utc(r["settlement_ts"]), reverse=True)
    window = eligible[:10]
    logs = []
    for m in window:
        floor = float(m["floor_strike"])
        if floor <= 0:
            continue
        logs.append(log(float(m["expiration_value"]) / floor))
    yes = sum(1 for m in window if str(m["result"]).lower() == "yes")
    no = sum(1 for m in window if str(m["result"]).lower() == "no")
    median = sorted(logs)[len(logs) // 2] if logs else 0.0
    return {
        "used": len(window),
        "yes": yes,
        "no": no,
        "median_logret": median,
        "tickers": [str(m.get("ticker") or "") for m in window],
    }


def last10_majority(stats: dict) -> str | None:
    if stats["used"] < 10 or stats["yes"] == stats["no"]:
        return None
    return "yes" if stats["yes"] > stats["no"] else "no"


def decision_times(market: dict):
    open_t = parse_utc(market["open_time"])
    return open_t, compute_t_star(open_t)
