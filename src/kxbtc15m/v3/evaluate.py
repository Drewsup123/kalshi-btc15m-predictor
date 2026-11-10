"""Offline historical replay pipeline. Holdout used once after lock."""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from kxbtc15m.clock import parse_utc, iso_utc
from kxbtc15m.v3 import MODEL_VERSION, FEATURE_SPEC, REPLAY_ASSUMPTION, KNN_K
from kxbtc15m.v3.asof import last10, last10_majority, opening_ref
from kxbtc15m.v3.candles import last_close
from kxbtc15m.v3.clock import t_star, t_pub_sim, time_left_seconds
from kxbtc15m.v3.controls import last_price_side, majority_side, no_change
from kxbtc15m.v3.features import FEATURE_NAMES, build_features, vector_array
from kxbtc15m.v3.lock import lock_payload, read_lock, write_lock
from kxbtc15m.v3.metrics import score_table
from kxbtc15m.v3.models import StandardScaler, fit_logistic, fit_ridge, knn_predict
from kxbtc15m.v3.split import chronological_split, walkforward_slices

L2_GRID = (0.01, 1.0, 10.0)


def _label_logret(market: dict) -> float:
    floor = float(market["floor_strike"])
    expv = float(market["expiration_value"])
    return math.log(expv / floor) if floor > 0 and expv > 0 else 0.0


def build_replay_rows(markets: list[dict], bars: list[dict]) -> list[dict]:
    ordered = sorted(markets, key=lambda m: parse_utc(m["close_time"]))
    rows = []
    for i, market in enumerate(ordered):
        open_t = parse_utc(market["open_time"])
        ts = t_star(open_t)
        priors = [m for j, m in enumerate(ordered) if j != i]
        s_t, s_src, skip_s = opening_ref(market, priors, ts, availability="historical_replay")
        r_t, r_end = last_close(bars, ts)
        l10 = last10(priors, ts, availability="historical_replay")
        vec, meta, skip_f = build_features(bars, l10, ts)
        skip = skip_s or skip_f
        if r_t is None and skip is None:
            skip = "missing_underlying"
        pub = t_pub_sim(open_t, ts)
        row = {
            "ticker": market.get("ticker"),
            "open_time": iso_utc(open_t),
            "close_time": iso_utc(market["close_time"]),
            "open_dt": open_t,
            "prediction_asof": iso_utc(ts),
            "t_pub_sim": iso_utc(pub) if pub else None,
            "availability": "historical_replay",
            "replay_assumption": REPLAY_ASSUMPTION,
            "S_t": s_t,
            "S_t_source": s_src,
            "R_t": r_t,
            "R_t_bar_end": iso_utc(r_end) if r_end else None,
            "floor_strike": float(market["floor_strike"]) if market.get("floor_strike") not in (None, "") else None,
            "expiration_value": float(market["expiration_value"]) if market.get("expiration_value") not in (None, "") else None,
            "result": str(market.get("result") or "").lower(),
            "settlement_ts": market.get("settlement_ts"),
            "y_log": _label_logret(market) if skip is None else None,
            "skip_reason": skip,
            "lead_bucket": "initial",
            "model_version": MODEL_VERSION,
            "feature_spec_hash": FEATURE_SPEC,
            "observation_at": None,
            "time_left": time_left_seconds(open_t, market["close_time"]),
            "last10": l10,
            "x": vector_array(vec) if vec else None,
            "meta": meta,
        }
        rows.append(row)
    return rows


def _train_matrices(train: list[dict]):
    x_train = np.array([r["x"] for r in train], dtype=float)
    y_cls = np.array([1 if r["result"] == "yes" else 0 for r in train], dtype=float)
    y_log = np.array([r["y_log"] for r in train], dtype=float)
    scaler = StandardScaler().fit(x_train)
    xs_train = scaler.transform(x_train)
    library = [
        {
            "x": xs_train[i],
            "label": int(y_cls[i]),
            "open": train[i]["open_dt"],
            "y_log": float(y_log[i]),
        }
        for i in range(len(train))
    ]
    return scaler, xs_train, y_cls, y_log, library, majority_side([r["result"] for r in train])


def _fit_locked(train: list[dict], l2_logistic: float, l2_ridge: float) -> dict:
    scaler, xs_train, y_cls, y_log, library, maj = _train_matrices(train)
    return {
        "scaler": scaler,
        "logistic": fit_logistic(xs_train, y_cls, l2=l2_logistic),
        "ridge": fit_ridge(xs_train, y_log, l2=l2_ridge),
        "l2_logistic": l2_logistic,
        "l2_ridge": l2_ridge,
        "library": library,
        "majority": maj,
        "val_logloss": None,
        "val_mae": None,
    }


def _fit_pick(train: list[dict], val: list[dict]) -> dict:
    scaler, xs_train, y_cls, y_log, library, maj = _train_matrices(train)
    x_val = scaler.transform(np.array([r["x"] for r in val], dtype=float))
    yv = np.array([1 if r["result"] == "yes" else 0 for r in val], dtype=float)
    ev = np.array([r["expiration_value"] for r in val], dtype=float)
    st = np.array([r["S_t"] for r in val], dtype=float)

    best_l2_log, best_ll = L2_GRID[0], float("inf")
    best_log = None
    for l2 in L2_GRID:
        m = fit_logistic(xs_train, y_cls, l2=l2)
        p = np.clip(m.predict_proba(x_val), 1e-12, 1 - 1e-12)
        ll = float(-np.mean(yv * np.log(p) + (1 - yv) * np.log(1 - p)))
        if ll < best_ll:
            best_ll, best_l2_log, best_log = ll, l2, m

    best_l2_ridge, best_mae, best_ridge = L2_GRID[0], float("inf"), None
    for l2 in L2_GRID:
        m = fit_ridge(xs_train, y_log, l2=l2)
        yhat = m.predict(x_val)
        fe = st * np.exp(yhat)
        mae = float(np.mean(np.abs(fe - ev)))
        if mae < best_mae:
            best_mae, best_l2_ridge, best_ridge = mae, l2, m

    return {
        "scaler": scaler,
        "logistic": best_log,
        "ridge": best_ridge,
        "l2_logistic": best_l2_log,
        "l2_ridge": best_l2_ridge,
        "library": library,
        "majority": maj,
        "val_logloss": best_ll,
        "val_mae": best_mae,
    }


def _apply(rows: list[dict], fit: dict) -> list[dict]:
    out = []
    for r in rows:
        item = dict(r)
        if r.get("skip_reason") or r.get("x") is None or r.get("S_t") is None:
            item["pred_yes"] = None
            item["p_yes"] = None
            item["forecast_end"] = None
            item["pred_yes_b"] = None
            item["pred_yes_majority"] = None
            item["pred_yes_last10"] = last10_majority(r.get("last10") or {})
            item["pred_yes_nochange"] = None
            item["pred_yes_lastprice"] = None
            item["forecast_end_b"] = None
            item["calibration"] = "uncalibrated"
            out.append(item)
            continue
        xs = fit["scaler"].transform(np.array([r["x"]], dtype=float))[0]
        p = float(fit["logistic"].predict_proba(xs.reshape(1, -1))[0])
        yhat = float(fit["ridge"].predict(xs.reshape(1, -1))[0])
        s_t = float(r["S_t"])
        forecast_end = s_t * math.exp(yhat)
        knn_pred, knn_p, knn_y = knn_predict(xs, t_star(r["open_dt"]), fit["library"], k=KNN_K)
        l10_side = last10_majority(r["last10"])
        nc_side, nc_y = no_change()
        item["pred_yes"] = "yes" if p >= 0.5 else "no"
        item["p_yes"] = p
        item["ŷ_log"] = yhat
        item["forecast_end"] = forecast_end
        item["pred_yes_aret"] = "yes" if forecast_end >= s_t else "no"
        item["pred_yes_b"] = None if knn_pred is None else ("yes" if knn_pred == 1 else "no")
        item["p_yes_b"] = knn_p
        item["forecast_end_b"] = None if knn_y is None else s_t * math.exp(knn_y)
        item["pred_yes_majority"] = fit["majority"]
        item["pred_yes_last10"] = l10_side
        item["pred_yes_nochange"] = nc_side
        item["forecast_end_nochange"] = s_t
        item["pred_yes_lastprice"] = last_price_side(float(r["R_t"]), s_t) if r.get("R_t") is not None else None
        item["forecast_end_lastprice"] = r.get("R_t")
        item["calibration"] = "uncalibrated"
        out.append(item)
    return out


def _remap(rows: list[dict], pred_key: str, forecast_key: str | None = None) -> list[dict]:
    out = []
    for r in rows:
        item = dict(r)
        pred = r.get(pred_key)
        skip = r.get("skip_reason")
        if pred is None and not skip:
            skip = "control_skip"
        item["pred_yes"] = pred
        item["skip_reason"] = skip
        if forecast_key:
            item["forecast_end"] = r.get(forecast_key)
        if pred_key == "pred_yes_b":
            item["p_yes"] = r.get("p_yes_b")
        elif pred_key != "pred_yes":
            item["p_yes"] = None
        out.append(item)
    return out


def _walkforward_diagnostic(rows: list[dict], l2_logistic: float, l2_ridge: float) -> dict:
    """Train/val stability only. Never sees holdout."""
    slices = walkforward_slices(rows)
    accs = []
    for train, test in slices:
        tr = [r for r in train if r.get("x") is not None and r.get("skip_reason") is None]
        te = [r for r in test if r.get("x") is not None and r.get("skip_reason") is None]
        if len(tr) < 20 or len(te) < 5:
            continue
        fit = _fit_locked(tr, l2_logistic, l2_ridge)
        pred = _apply(te, fit)
        table = score_table(pred)
        if table["accuracy"] is not None:
            accs.append(table["accuracy"])
    return {
        "n_slices": len(accs),
        "mean_accuracy": (sum(accs) / len(accs)) if accs else None,
        "embargo_minutes": 111,
        "split_used": "train+validation",
    }


def evaluate_rows(rows: list[dict], state_dir: Path, dataset_asof: str) -> dict:
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    train, val, holdout = chronological_split(rows)
    train_fit = [r for r in train if r.get("x") is not None and r.get("skip_reason") is None]
    val_fit = [r for r in val if r.get("x") is not None and r.get("skip_reason") is None]
    if len(train_fit) < 20 or len(val_fit) < 5:
        raise RuntimeError("not enough usable rows to split 70/15/15")
    lock_path = state_dir / "lock.json"
    if lock_path.exists():
        existing = read_lock(lock_path)
        fit = _fit_locked(train_fit, float(existing["l2_logistic"]), float(existing["l2_ridge"]))
        payload = existing
    else:
        fit = _fit_pick(train_fit, val_fit)
        payload = lock_payload(
            fit["l2_logistic"],
            fit["l2_ridge"],
            extra={
                "n_train": len(train_fit),
                "n_val": len(val_fit),
                "n_holdout": len(holdout),
                "val_logloss": fit["val_logloss"],
                "val_mae": fit["val_mae"],
                "dataset_asof": dataset_asof,
            },
        )
        write_lock(lock_path, payload)

    labeled = []
    for r in train:
        r = dict(r)
        r["split"] = "train"
        labeled.append(r)
    for r in val:
        r = dict(r)
        r["split"] = "validation"
        labeled.append(r)
    for r in holdout:
        r = dict(r)
        r["split"] = "holdout"
        labeled.append(r)
    predicted = _apply(labeled, fit)
    for r in predicted:
        r["run_generated_at"] = run_at
        r["dataset_asof"] = dataset_asof
        r.pop("x", None)
        r.pop("open_dt", None)
        r.pop("meta", None)
        r.pop("last10", None)

    holdout_pred = [r for r in predicted if r.get("split") == "holdout"]
    tables = {
        "A_logistic": score_table(holdout_pred),
        "A_ret": score_table(_remap(holdout_pred, "pred_yes_aret", "forecast_end")),
        "B_knn": score_table(_remap(holdout_pred, "pred_yes_b", "forecast_end_b")),
        "C_majority": score_table(_remap(holdout_pred, "pred_yes_majority", "forecast_end_nochange")),
        "C_last10": score_table(_remap(holdout_pred, "pred_yes_last10", "forecast_end_nochange")),
        "C_nochange": score_table(_remap(holdout_pred, "pred_yes_nochange", "forecast_end_nochange")),
        "C_lastprice": score_table(_remap(holdout_pred, "pred_yes_lastprice", "forecast_end_lastprice")),
    }
    metrics = {
        "availability": "historical_replay",
        "replay_assumption": REPLAY_ASSUMPTION,
        "model_version": MODEL_VERSION,
        "dataset_asof": dataset_asof,
        "run_generated_at": run_at,
        "n_inventory_scored_universe": len(rows),
        "n_usable": len(train_fit) + len(val_fit) + len([r for r in holdout if not r.get("skip_reason")]),
        "n_skipped": len([r for r in rows if r.get("skip_reason")]),
        "n_train": len(train_fit),
        "n_validation": len(val_fit),
        "n_holdout": len(holdout),
        "lock": payload,
        "walkforward": _walkforward_diagnostic(train + val, fit["l2_logistic"], fit["l2_ridge"]),
        "holdout": tables,
        "aspiration": {"low": 0.80, "high": 0.90, "note": "display reference only; not a pass condition"},
        "calibration": "uncalibrated",
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str) + "\n", encoding="utf-8")
    fieldnames = [
        "ticker",
        "split",
        "open_time",
        "close_time",
        "prediction_asof",
        "t_pub_sim",
        "run_generated_at",
        "dataset_asof",
        "availability",
        "replay_assumption",
        "S_t",
        "R_t",
        "pred_yes",
        "p_yes",
        "forecast_end",
        "result",
        "expiration_value",
        "floor_strike",
        "skip_reason",
        "pred_yes_b",
        "pred_yes_majority",
        "pred_yes_last10",
        "pred_yes_nochange",
        "pred_yes_lastprice",
        "model_version",
        "calibration",
    ]
    with (state_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in predicted:
            writer.writerow(r)
    return metrics
