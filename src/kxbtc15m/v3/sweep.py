"""Pre-registered strategy sweep. Selection on train/val only. No holdout tuning."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from kxbtc15m.clock import parse_utc
from kxbtc15m.v3.asof import last10_majority
from kxbtc15m.v3.controls import last_price_side, majority_side
from kxbtc15m.v3.evaluate import build_replay_rows
from kxbtc15m.v3.metrics import score_table
from kxbtc15m.v3.models import StandardScaler, fit_logistic, knn_predict, knn_predict_matrix
from kxbtc15m.v3.split import chronological_split, walkforward_slices

OFFSETS = (30, 60, 120, 300, 420, 600, 720, 840)
PREOPEN_OFFSET = 0
SELECTIVE_C = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)
KNN_SPARSE = {30: (11, 51), 300: (11, 51), 840: (11, 51)}
LOCKED_L2 = 10.0
TARGET_ACC = 0.75
EMBARGO = timedelta(minutes=111)

try:
    from sklearn.ensemble import HistGradientBoostingClassifier

    HAS_HGB = True
except Exception:
    HistGradientBoostingClassifier = None
    HAS_HGB = False


def _usable(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("x") is not None and r.get("skip_reason") is None and r.get("S_t") is not None]


def _embargoed_val(train: list[dict], val: list[dict]) -> list[dict]:
    if not train:
        return val
    cut = parse_utc(train[-1]["close_time"]) + EMBARGO
    return [r for r in val if parse_utc(r["close_time"]) > cut]


def _record(variant_id: str, offset_s: int, table: dict, split_label: str, extra: dict | None = None) -> dict:
    row = {
        "id": variant_id,
        "offset_s": offset_s,
        "split": split_label,
        "accuracy": table.get("accuracy"),
        "wilson_lo": table.get("wilson_lo"),
        "wilson_hi": table.get("wilson_hi"),
        "coverage": table.get("coverage"),
        "n_scored": table.get("n_scored"),
        "n_skip": table.get("n_skip"),
        "n_total": table.get("n_total"),
        "mae": table.get("mae"),
    }
    if extra:
        row.update(extra)
    return row


def _clone_pred(row: dict, pred: str | None, p_yes: float | None, skip: str | None, forecast_end=None) -> dict:
    item = {
        "ticker": row.get("ticker"),
        "close_time": row.get("close_time"),
        "open_time": row.get("open_time"),
        "open_dt": row.get("open_dt"),
        "result": row.get("result"),
        "expiration_value": row.get("expiration_value"),
        "S_t": row.get("S_t"),
        "R_t": row.get("R_t"),
        "pred_yes": pred,
        "p_yes": p_yes,
        "skip_reason": skip or row.get("skip_reason"),
        "forecast_end": forecast_end if forecast_end is not None else row.get("R_t"),
    }
    if item["skip_reason"] and not skip:
        item["pred_yes"] = None
    if pred is None and not item["skip_reason"]:
        item["skip_reason"] = "control_skip"
    return item


def _fit_models(train: list[dict]) -> dict:
    usable = _usable(train)
    fit = {"majority": majority_side([r["result"] for r in usable] or ["yes"])}
    atrs = [float(r["atr16"]) for r in usable if r.get("atr16") is not None]
    fit["atr_median"] = sorted(atrs)[len(atrs) // 2] if atrs else 0.0
    if len(usable) < 20:
        return fit
    x = np.array([r["x"] for r in usable], dtype=float)
    y = np.array([1 if r["result"] == "yes" else 0 for r in usable], dtype=float)
    scaler = StandardScaler().fit(x)
    xs = scaler.transform(x)
    fit["scaler"] = scaler
    fit["logistic"] = fit_logistic(xs, y, l2=LOCKED_L2)
    zfeat = []
    for r in usable:
        zfeat.append(
            list(r["x"])
            + [
                float(r["z_16"] if r.get("z_16") is not None else 0.0),
                math.log(max(float(r.get("tau_minutes") or 1.0), 1e-6)),
            ]
        )
    xz = np.array(zfeat, dtype=float)
    scaler_z = StandardScaler().fit(xz)
    fit["scaler_z"] = scaler_z
    fit["logistic_z"] = fit_logistic(scaler_z.transform(xz), y, l2=LOCKED_L2)
    fit["library"] = [
        {
            "x": xs[i],
            "label": int(y[i]),
            "open": usable[i]["open_dt"],
            "y_log": float(usable[i]["y_log"] or 0.0),
        }
        for i in range(len(usable))
    ]
    fit["knn_X"] = xs
    fit["knn_opens"] = np.array([u["open_dt"].timestamp() for u in usable], dtype=float)
    fit["knn_labels"] = y.astype(int)
    fit["knn_ylog"] = np.array([float(u["y_log"] or 0.0) for u in usable], dtype=float)
    if HAS_HGB:
        hgb = HistGradientBoostingClassifier(
            max_depth=3, max_iter=80, learning_rate=0.05, random_state=0
        )
        hgb.fit(xs, y)
        fit["hgb"] = hgb
    return fit


def _x_z(row: dict) -> np.ndarray | None:
    if row.get("x") is None:
        return None
    return np.array(
        list(row["x"])
        + [
            float(row["z_16"] if row.get("z_16") is not None else 0.0),
            math.log(max(float(row.get("tau_minutes") or 1.0), 1e-6)),
        ],
        dtype=float,
    )


def apply_family(rows: list[dict], family: str, fit: dict, k: int | None = None) -> list[dict]:
    out = []
    maj = fit.get("majority") or "yes"
    atr_med = float(fit.get("atr_median") or 0.0)
    for r in rows:
        base_skip = r.get("skip_reason")
        s_t, r_t = r.get("S_t"), r.get("R_t")
        if family == "C_lastprice":
            if base_skip or s_t is None or r_t is None:
                out.append(_clone_pred(r, None, None, base_skip or "missing_underlying"))
            else:
                pred = last_price_side(float(r_t), float(s_t))
                out.append(_clone_pred(r, pred, 1.0 if pred == "yes" else 0.0, None, r_t))
            continue
        if family == "C_nochange":
            if base_skip or s_t is None:
                out.append(_clone_pred(r, None, None, base_skip or "insufficient_opening_ref"))
            else:
                out.append(_clone_pred(r, "yes", 1.0, None, s_t))
            continue
        if family == "C_majority":
            if base_skip:
                out.append(_clone_pred(r, None, None, base_skip))
            else:
                out.append(_clone_pred(r, maj, None, None, r_t))
            continue
        if family == "C_last10":
            side = last10_majority(r.get("last10") or {})
            out.append(_clone_pred(r, side, None, None if side else "control_skip", r_t))
            continue
        if family == "D_brownian_16":
            p = r.get("p_brownian_16")
            if base_skip or p is None:
                out.append(_clone_pred(r, None, p, base_skip or "missing_underlying"))
            else:
                out.append(_clone_pred(r, "yes" if p >= 0.5 else "no", float(p), None, r_t))
            continue
        if family == "D_brownian_96":
            p = r.get("p_brownian_96")
            if base_skip or p is None:
                out.append(_clone_pred(r, None, p, base_skip or "missing_underlying"))
            else:
                out.append(_clone_pred(r, "yes" if p >= 0.5 else "no", float(p), None, r_t))
            continue
        if family == "I_yes_last":
            px = r.get("yes_price_asof")
            if px is None:
                out.append(_clone_pred(r, None, None, "implied_unavailable"))
            else:
                pred = "yes" if float(px) >= 0.5 else "no"
                out.append(_clone_pred(r, pred, float(px), None, r_t))
            continue
        if family == "E_regime_trend":
            if base_skip or s_t is None or r_t is None:
                out.append(_clone_pred(r, None, None, base_skip or "missing_underlying"))
            else:
                pred = last_price_side(float(r_t), float(s_t))
                out.append(_clone_pred(r, pred, 1.0 if pred == "yes" else 0.0, None, r_t))
            continue
        if family == "E_regime_vol":
            if base_skip or s_t is None or r_t is None:
                out.append(_clone_pred(r, None, None, base_skip or "missing_underlying"))
            else:
                atr = r.get("atr16")
                if atr is None or float(atr) < atr_med:
                    pred = maj
                    p = None
                else:
                    pred = last_price_side(float(r_t), float(s_t))
                    p = 1.0 if pred == "yes" else 0.0
                out.append(_clone_pred(r, pred, p, None, r_t))
            continue
        if family in {"A_logistic", "A_logistic_z", "A_hgb"} or family.startswith("B_knn"):
            if base_skip or r.get("x") is None or s_t is None:
                out.append(_clone_pred(r, None, None, base_skip or "missing_underlying"))
                continue
            scaler = fit.get("scaler")
            if scaler is None:
                out.append(_clone_pred(r, None, None, "not_trained"))
                continue
            xs = scaler.transform(np.array([r["x"]], dtype=float))[0]
            if family == "A_logistic":
                p = float(fit["logistic"].predict_proba(xs.reshape(1, -1))[0])
                out.append(_clone_pred(r, "yes" if p >= 0.5 else "no", p, None, r_t))
                continue
            if family == "A_logistic_z":
                xz = _x_z(r).reshape(1, -1)
                p = float(fit["logistic_z"].predict_proba(fit["scaler_z"].transform(xz))[0])
                out.append(_clone_pred(r, "yes" if p >= 0.5 else "no", p, None, r_t))
                continue
            if family == "A_hgb":
                hgb = fit.get("hgb")
                if hgb is None:
                    out.append(_clone_pred(r, None, None, "hgb_unavailable"))
                else:
                    p = float(hgb.predict_proba(xs.reshape(1, -1))[0, 1])
                    out.append(_clone_pred(r, "yes" if p >= 0.5 else "no", p, None, r_t))
                continue
            kk = k or 25
            tdec = r.get("open_dt")
            if tdec is None:
                tdec = parse_utc(r["open_time"])
            from kxbtc15m.v3.clock import decision_time

            t_ts = decision_time(tdec, r.get("decision_offset_s") or 30).timestamp()
            if fit.get("knn_X") is not None:
                pred, p, _y = knn_predict_matrix(
                    xs, t_ts, fit["knn_X"], fit["knn_opens"], fit["knn_labels"], fit["knn_ylog"], k=kk
                )
            else:
                pred, p, _y = knn_predict(xs, decision_time(tdec, r.get("decision_offset_s") or 30), fit.get("library") or [], k=kk)
            if pred is None:
                out.append(_clone_pred(r, None, None, "knn_skip"))
            else:
                out.append(_clone_pred(r, "yes" if pred == 1 else "no", p, None, r_t))
            continue
        out.append(_clone_pred(r, None, None, "unknown_family"))
    return out


def apply_vote(rows: list[dict], fit: dict) -> list[dict]:
    a = apply_family(rows, "C_lastprice", fit)
    b = apply_family(rows, "D_brownian_16", fit)
    c = apply_family(rows, "A_logistic", fit)
    out = []
    for x, y, z, src in zip(a, b, c, rows):
        votes = [p["pred_yes"] for p in (x, y, z) if p.get("pred_yes") in {"yes", "no"}]
        if len(votes) < 2:
            out.append(_clone_pred(src, None, None, src.get("skip_reason") or "control_skip"))
            continue
        yes = sum(1 for v in votes if v == "yes")
        pred = "yes" if yes > len(votes) / 2 else "no"
        if yes == len(votes) / 2:
            out.append(_clone_pred(src, None, None, "vote_tie"))
        else:
            p = yes / len(votes)
            out.append(_clone_pred(src, pred, p, None, src.get("R_t")))
    return out


def apply_selective(predicted: list[dict], c: float) -> list[dict]:
    out = []
    for r in predicted:
        item = dict(r)
        p = item.get("p_yes")
        if item.get("skip_reason"):
            out.append(item)
            continue
        if p is None or abs(float(p) - 0.5) < c:
            item["skip_reason"] = "low_confidence"
            item["pred_yes"] = None
        out.append(item)
    return out


def _wf_mean(train_val: list[dict], family: str, k: int | None = None) -> tuple[float | None, float | None, int]:
    accs, covs = [], []
    for tr, te in walkforward_slices(train_val):
        fit = {"majority": majority_side([r["result"] for r in _usable(tr)] or ["yes"])}
        atrs = [float(r["atr16"]) for r in _usable(tr) if r.get("atr16") is not None]
        fit["atr_median"] = sorted(atrs)[len(atrs) // 2] if atrs else 0.0
        if family in {"A_logistic", "A_logistic_z", "A_hgb", "F_vote"} or str(family).startswith("B_knn"):
            fit = _fit_models(tr)
        if family == "F_vote":
            pred = apply_vote(te, fit)
        else:
            pred = apply_family(te, family, fit, k=k)
        table = score_table(pred)
        if table["accuracy"] is not None:
            accs.append(table["accuracy"])
            covs.append(table["coverage"] or 0.0)
    if not accs:
        return None, None, 0
    return sum(accs) / len(accs), sum(covs) / len(covs), len(accs)


def families_for_offset(offset_s: int) -> list[tuple[str, int | None]]:
    fams = [
        ("C_lastprice", None),
        ("C_nochange", None),
        ("C_majority", None),
        ("C_last10", None),
        ("D_brownian_16", None),
        ("D_brownian_96", None),
        ("A_logistic", None),
        ("A_logistic_z", None),
        ("A_hgb", None),
        ("B_knn_k25", 25),
        ("E_regime_trend", None),
        ("E_regime_vol", None),
        ("F_vote", None),
        ("I_yes_last", None),
    ]
    for k in KNN_SPARSE.get(offset_s, ()):
        fams.append((f"B_knn_k{k}", k))
    return fams


def select_best(val_rows: list[dict]) -> dict:
    """val_rows are records with split=validation (walk-forward or embargoed val)."""
    eligible_75 = [r for r in val_rows if r.get("accuracy") is not None and r["accuracy"] >= TARGET_ACC]
    if eligible_75:
        best = max(eligible_75, key=lambda r: (r.get("coverage") or 0.0, r.get("accuracy") or 0.0))
        rule = "max_coverage_among_wf_ge_75"
    else:
        ranked = [r for r in val_rows if r.get("accuracy") is not None]
        if not ranked:
            raise RuntimeError("no validation accuracies")
        best = max(ranked, key=lambda r: r["accuracy"])
        rule = "max_wf_accuracy"
    return {"rule": rule, "chosen": best, "target": TARGET_ACC}


def run_sweep(
    markets: list[dict],
    bars: list[dict],
    state_dir: Path,
    dataset_asof: str,
    lock_dataset_asof: str | None = None,
) -> dict:
    state_dir = Path(state_dir)
    sweep_dir = state_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records: list[dict] = []
    holdout_records: list[dict] = []
    preopen_holdout = None
    offsets = (PREOPEN_OFFSET,) + OFFSETS

    lock_asof = lock_dataset_asof or dataset_asof
    lock_dt = parse_utc(lock_asof)
    fresh = [m for m in markets if parse_utc(m["close_time"]) > lock_dt]
    use_fresh = len(fresh) >= 200
    holdout_label = "holdout_fresh" if use_fresh else "holdout_previously_viewed"

    for offset_s in offsets:
        rows = build_replay_rows(markets, bars, offset_seconds=offset_s)
        from kxbtc15m.v3.implied import last_yes_asof, load_cached_trades

        for r in rows:
            trades = load_cached_trades(state_dir, r["ticker"])
            if trades:
                r["yes_price_asof"] = last_yes_asof(trades, parse_utc(r["prediction_asof"]))
        train, val, holdout = chronological_split(rows)
        if use_fresh:
            holdout = [r for r in rows if parse_utc(r["close_time"]) > lock_dt]
        val_e = _embargoed_val(train, val)
        train_val = train + val
        fit = _fit_models(train)
        cheap = {"C_lastprice", "C_nochange", "C_majority", "C_last10", "D_brownian_16", "D_brownian_96", "E_regime_trend", "E_regime_vol", "I_yes_last"}
        for family, k in families_for_offset(offset_s):
            vid = f"{family}@t+{offset_s}s" if offset_s else f"{family}@preopen"
            if family == "F_vote":
                pred_val = apply_vote(val_e, fit)
                pred_ho = apply_vote(holdout, fit)
            else:
                pred_val = apply_family(val_e, family, fit, k=k)
                pred_ho = apply_family(holdout, family, fit, k=k)
            val_table = score_table(pred_val)
            ho_table = score_table(pred_ho)
            wf_acc = wf_cov = None
            wf_n = 0
            if family in cheap:
                wf_acc, wf_cov, wf_n = _wf_mean(train_val, family, k=k)
            select_acc = wf_acc if wf_acc is not None else val_table.get("accuracy")
            select_cov = wf_cov if wf_cov is not None else val_table.get("coverage")
            rec = _record(
                vid,
                offset_s,
                {
                    "accuracy": select_acc,
                    "wilson_lo": val_table.get("wilson_lo"),
                    "wilson_hi": val_table.get("wilson_hi"),
                    "coverage": select_cov,
                    "n_scored": val_table.get("n_scored"),
                    "n_skip": val_table.get("n_skip"),
                    "n_total": val_table.get("n_total"),
                    "mae": val_table.get("mae"),
                },
                "train_val_walkforward" if wf_acc is not None else "embargoed_validation",
                extra={"family": family, "k": k, "wf_slices": wf_n, "val_accuracy": val_table.get("accuracy")},
            )
            records.append(rec)
            holdout_records.append(
                _record(
                    vid,
                    offset_s,
                    ho_table,
                    holdout_label,
                    extra={"family": family, "k": k, "n_fresh": len(fresh)},
                )
            )
            if family in {"D_brownian_16", "A_logistic_z"}:
                for c in SELECTIVE_C:
                    sid = f"S_{family}_c{c:.2f}@t+{offset_s}s" if offset_s else f"S_{family}_c{c:.2f}@preopen"
                    sel_val = score_table(apply_selective(pred_val, c))
                    sel_ho = score_table(apply_selective(pred_ho, c))
                    sel_acc = sel_val.get("accuracy")
                    records.append(
                        _record(
                            sid,
                            offset_s,
                            sel_val,
                            "embargoed_validation",
                            extra={"family": f"S_{family}", "threshold": c, "parent": vid},
                        )
                    )
                    holdout_records.append(
                        _record(
                            sid,
                            offset_s,
                            sel_ho,
                            holdout_label,
                            extra={"family": f"S_{family}", "threshold": c, "parent": vid, "n_fresh": len(fresh)},
                        )
                    )
            if offset_s == PREOPEN_OFFSET and family == "A_logistic_z":
                preopen_holdout = ho_table
        print(f"sweep offset {offset_s}s families done", flush=True)

    selection = select_best(records)
    payload = {
        "run_generated_at": run_at,
        "dataset_asof": dataset_asof,
        "lock_dataset_asof": lock_asof,
        "n_fresh": len(fresh),
        "holdout_label": holdout_label,
        "n_variants_tried": len(records),
        "has_hgb": HAS_HGB,
        "multiple_comparisons": (
            "Holdout numbers are previously viewed" if holdout_label == "holdout_previously_viewed"
            else "Fresh windows after lock dataset_asof; still one look after selection."
        )
        + f" {len(records)} variants were compared on train/val. Unadjusted Wilson intervals do not correct for the search.",
        "selection": selection,
        "target_accuracy": TARGET_ACC,
        "aspiration_note": "75% is a target, not a pass condition",
    }
    (sweep_dir / "selection.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (sweep_dir / "variants_val.json").write_text(json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8")
    (sweep_dir / "variants_holdout.json").write_text(json.dumps(holdout_records, indent=2, default=str) + "\n", encoding="utf-8")
    payload["validation"] = records
    payload["holdout"] = holdout_records
    payload["preopen_holdout"] = preopen_holdout
    (sweep_dir / "summary.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return payload
