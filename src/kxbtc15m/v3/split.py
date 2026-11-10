"""Chronological 70/15/15 and walk-forward with embargo. No random split."""

from __future__ import annotations

from datetime import timedelta

from kxbtc15m.clock import parse_utc
from kxbtc15m.v3 import EMBARGO_MINUTES


def _close(row: dict):
    return parse_utc(row["close_time"]) if not hasattr(row["close_time"], "tzinfo") else row["close_time"]


def chronological_split(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    ordered = sorted(rows, key=_close)
    n = len(ordered)
    n_train = int(n * 0.70)
    n_val = int(n * 0.15)
    train = ordered[:n_train]
    val = ordered[n_train : n_train + n_val]
    holdout = ordered[n_train + n_val :]
    return train, val, holdout


def walkforward_slices(
    rows: list[dict],
    slice_days: int = 7,
    embargo_minutes: int = EMBARGO_MINUTES,
) -> list[tuple[list[dict], list[dict]]]:
    ordered = sorted(rows, key=_close)
    if len(ordered) < 4:
        return []
    embargo = timedelta(minutes=embargo_minutes)
    start = _close(ordered[0])
    end = _close(ordered[-1])
    slices = []
    origin = start
    slice_delta = timedelta(days=slice_days)
    while origin < end:
        origin_end = origin + slice_delta
        train = [r for r in ordered if _close(r) <= origin_end]
        test_lo = origin_end + embargo
        test_hi = test_lo + slice_delta
        test = [r for r in ordered if test_lo < _close(r) <= test_hi]
        if train and test:
            slices.append((train, test))
        origin = origin_end
        if origin_end >= end:
            break
    return slices
