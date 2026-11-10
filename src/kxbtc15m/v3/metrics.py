"""Replay metrics. Skip ≠ error. Empty report has no accuracy number."""

from __future__ import annotations

import math
import random
from typing import Iterable


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / den
    return center - half, center + half


def empty_metrics() -> dict:
    return {
        "n_scored": 0,
        "n_skip": 0,
        "n_total": 0,
        "accuracy": None,
        "coverage": None,
        "wilson_lo": None,
        "wilson_hi": None,
        "mae": None,
        "bias": None,
        "brier": None,
        "logloss": None,
        "confusion": {"tp": 0, "tn": 0, "fp": 0, "fn": 0},
        "skip_reasons": {},
        "yes_rate_actual": None,
        "availability": "historical_replay",
        "calibration": "uncalibrated",
    }


def score_table(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    scored = [r for r in rows if not r.get("skip_reason") and r.get("pred_yes") in {"yes", "no"}]
    skipped = [r for r in rows if r.get("skip_reason")]
    m = empty_metrics()
    m["n_scored"] = len(scored)
    m["n_skip"] = len(skipped)
    m["n_total"] = len(rows)
    reasons: dict[str, int] = {}
    for r in skipped:
        reasons[str(r["skip_reason"])] = reasons.get(str(r["skip_reason"]), 0) + 1
    m["skip_reasons"] = reasons
    if not rows:
        return m
    m["coverage"] = len(scored) / len(rows) if rows else None
    if not scored:
        return m
    correct = 0
    tp = tn = fp = fn = 0
    abs_err = []
    signed = []
    brier_acc = []
    logloss_acc = []
    actual_yes = 0
    for r in scored:
        pred = str(r["pred_yes"]).lower()
        actual = str(r["result"]).lower()
        actual_yes += int(actual == "yes")
        hit = pred == actual
        correct += int(hit)
        if pred == "yes" and actual == "yes":
            tp += 1
        elif pred == "no" and actual == "no":
            tn += 1
        elif pred == "yes" and actual == "no":
            fp += 1
        else:
            fn += 1
        fe, ev = r.get("forecast_end"), r.get("expiration_value")
        if fe is not None and ev not in (None, ""):
            err = float(fe) - float(ev)
            abs_err.append(abs(err))
            signed.append(err)
        p = r.get("p_yes")
        if p is not None:
            y = 1.0 if actual == "yes" else 0.0
            p = min(max(float(p), 1e-12), 1 - 1e-12)
            brier_acc.append((p - y) ** 2)
            logloss_acc.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    n = len(scored)
    m["accuracy"] = correct / n
    m["wilson_lo"], m["wilson_hi"] = wilson_interval(correct, n)
    m["confusion"] = {"tp": tp, "tn": tn, "fp": fp, "fn": fn}
    m["yes_rate_actual"] = actual_yes / n
    if abs_err:
        m["mae"] = sum(abs_err) / len(abs_err)
        m["bias"] = sum(signed) / len(signed)
    if brier_acc:
        m["brier"] = sum(brier_acc) / len(brier_acc)
        m["logloss"] = sum(logloss_acc) / len(logloss_acc)
    return m


def permutation_disclosure(rows: list[dict], split_allowed: tuple[str, ...] = ("validation",)) -> dict:
    if any(str(r.get("split")) not in split_allowed for r in rows):
        raise ValueError("permutation diagnostic refused for disallowed split")
    shuffled = []
    labels = [r["result"] for r in rows]
    random.Random(0).shuffle(labels)
    for r, lab in zip(rows, labels):
        item = dict(r)
        item["result"] = lab
        shuffled.append(item)
    return score_table(shuffled)
