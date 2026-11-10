"""Normalized chart-shape vector. No raw USD residuals."""

from __future__ import annotations

from datetime import datetime
from math import log

from kxbtc15m.v3.candles import filter_completed
from kxbtc15m.v3 import CORE_BARS, LOOKBACK_BARS

FEATURE_NAMES = (
    "logret_1",
    "logret_4",
    "logret_16",
    "logret_96",
    "zret_1",
    "zret_4",
    "zret_16",
    "zret_96",
    "rel_volume",
    "range_pct",
    "atr16_pct",
    "upper_wick",
    "lower_wick",
    "close_loc",
    "last10_yes",
    "last10_no",
    "last10_used",
    "last10_median_logret",
    "missing_lookback96",
    "missing_last10",
    "missing_pressure",
)

EPS = 1e-12


def _closes(bars: list[dict]) -> list[float]:
    return [float(b["close"]) for b in bars]


def _logret(closes: list[float], h: int) -> float:
    if len(closes) <= h or closes[-1 - h] <= 0 or closes[-1] <= 0:
        return 0.0
    return log(closes[-1] / closes[-1 - h])


def build_features(
    bars: list[dict],
    last10: dict,
    t_star: datetime,
) -> tuple[dict | None, dict, str | None]:
    done = filter_completed(bars, t_star)
    if len(done) < CORE_BARS + 1:
        return None, {"n_bars": len(done)}, "missing_underlying"
    closes = _closes(done)
    last = done[-1]
    high, low, close, opn = float(last["high"]), float(last["low"]), float(last["close"]), float(last["open"])
    rng = max(high - low, EPS)
    rets1 = []
    for i in range(1, min(16, len(closes))):
        if closes[-1 - i] > 0 and closes[-i] > 0:
            rets1.append(log(closes[-i] / closes[-1 - i]))
    vol = (sum(r * r for r in rets1) / max(len(rets1), 1)) ** 0.5
    vol = max(vol, EPS)
    vols = [float(b["volume"]) for b in done[-LOOKBACK_BARS:]]
    med_vol = sorted(vols)[len(vols) // 2] if vols else 1.0
    med_vol = max(med_vol, EPS)
    ranges = [(float(b["high"]) - float(b["low"])) / max(float(b["close"]), EPS) for b in done[-16:]]
    atr16 = sum(ranges) / max(len(ranges), 1)
    missing96 = 0.0 if len(done) > LOOKBACK_BARS else 1.0
    missing_last10 = 0.0 if last10.get("used", 0) >= 10 else 1.0
    vec = {
        "logret_1": _logret(closes, 1),
        "logret_4": _logret(closes, 4),
        "logret_16": _logret(closes, 16),
        "logret_96": _logret(closes, 96) if missing96 == 0.0 else 0.0,
        "zret_1": _logret(closes, 1) / vol,
        "zret_4": _logret(closes, 4) / vol,
        "zret_16": _logret(closes, 16) / vol,
        "zret_96": (_logret(closes, 96) / vol) if missing96 == 0.0 else 0.0,
        "rel_volume": float(last["volume"]) / med_vol,
        "range_pct": rng / max(close, EPS),
        "atr16_pct": atr16,
        "upper_wick": (high - max(close, opn)) / rng,
        "lower_wick": (min(close, opn) - low) / rng,
        "close_loc": (close - low) / rng,
        "last10_yes": float(last10.get("yes") or 0),
        "last10_no": float(last10.get("no") or 0),
        "last10_used": float(last10.get("used") or 0),
        "last10_median_logret": float(last10.get("median_logret") or 0.0),
        "missing_lookback96": missing96,
        "missing_last10": missing_last10,
        "missing_pressure": 1.0,
    }
    meta = {"n_bars": len(done), "last_bar_start": done[-1]["start"].isoformat()}
    return vec, meta, None


def vector_array(vec: dict) -> list[float]:
    return [float(vec[name]) for name in FEATURE_NAMES]
