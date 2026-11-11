"""Hero presentation helpers: confidence, why-text, consistency, % formatting.

Never invents figures — only maps/model outputs already present on the card.
"""

from __future__ import annotations

from typing import Any


# Call-side confidence thresholds (documented in design spec).
# Low:  < 55%; Medium: 55–64%; High: ≥ 65%.
CONFIDENCE_LOW_MAX = 55
CONFIDENCE_MED_MAX = 65


def confidence_from_p(p_yes: float | None, pred_yes: str | None) -> dict[str, Any]:
    """Map classifier p_yes + side to confidence_pct, Low/Medium/High, UP/DOWN."""
    direction = None
    side = str(pred_yes or "").lower()
    if side == "yes":
        direction = "UP"
    elif side == "no":
        direction = "DOWN"
    if p_yes is None or direction is None:
        return {
            "direction": direction,
            "p_call": None,
            "confidence_pct": None,
            "label": None,
        }
    p = float(p_yes)
    p_call = p if side == "yes" else (1.0 - p)
    pct = int(round(100.0 * p_call))
    if pct < CONFIDENCE_LOW_MAX:
        label = "Low"
    elif pct < CONFIDENCE_MED_MAX:
        label = "Medium"
    else:
        label = "High"
    return {
        "direction": direction,
        "p_call": p_call,
        "confidence_pct": pct,
        "label": label,
    }


def end_price_agrees_with_direction(
    pred_yes: str | None,
    s_t: float | None,
    forecast_end: float | None,
) -> bool | None:
    if pred_yes not in {"yes", "no"} or s_t is None or forecast_end is None:
        return None
    end_says_yes = float(forecast_end) >= float(s_t)
    return end_says_yes == (pred_yes == "yes")


def consistent_forecast_end(
    pred_yes: str | None,
    s_t: float | None,
    forecast_end: float | None,
) -> tuple[float | None, str]:
    """Return (value, mode) where mode is show|hide|unavailable."""
    if forecast_end is None or s_t is None or pred_yes not in {"yes", "no"}:
        return None, "unavailable"
    if end_price_agrees_with_direction(pred_yes, s_t, forecast_end):
        return float(forecast_end), "show"
    return None, "hide"


def _minutes_left_phrase(time_left_s: float | None) -> str | None:
    if time_left_s is None:
        return None
    mins = int(max(0.0, float(time_left_s)) // 60)
    if mins == 1:
        return "1 minute left"
    return f"{mins} minutes left"


def why_sentences(card: dict) -> str:
    """One or two plain-English sentences from observed card fields only."""
    parts: list[str] = []
    s_t = card.get("S_t")
    r_t = card.get("R_t")
    time_left = card.get("time_left_s")
    if time_left is None and card.get("time_left") is not None:
        time_left = card.get("time_left")
    if s_t is not None and r_t is not None:
        delta = float(r_t) - float(s_t)
        abs_d = abs(delta)
        if abs_d >= 10:
            money = f"${abs_d:,.0f}"
        elif abs_d >= 1:
            money = f"${abs_d:,.2f}"
        else:
            money = f"${abs_d:,.2f}"
        relation = "above" if delta >= 0 else "below"
        clause = f"BTC is {money} {relation} the open"
        left = _minutes_left_phrase(time_left)
        if left:
            clause += f" with {left}"
        parts.append(clause + ".")
    logret_1 = card.get("logret_1")
    if logret_1 is not None and abs(float(logret_1)) >= 1e-5:
        mom = "up" if float(logret_1) > 0 else "down"
        parts.append(f"Recent 1-minute momentum is {mom}.")
    last10 = card.get("last10_side") or card.get("last10_majority")
    if last10 in {"yes", "no"} and len(parts) < 2:
        side = "UP" if last10 == "yes" else "DOWN"
        parts.append(f"The last-10 settled windows lean {side}.")
    if not parts:
        return "Not enough live features yet to explain this call."
    return " ".join(parts[:2])


def format_correct_summary(n_correct: int, n_scored: int) -> str | None:
    if n_scored <= 0:
        return None
    pct = int(round(100.0 * float(n_correct) / float(n_scored)))
    return f"{n_correct} of {n_scored} correct ({pct}%)"


def historical_accuracy_at(
    holdout_rows: list[dict] | None,
    family: str | None,
    offset_s: int | None,
) -> dict | None:
    if not holdout_rows or not family or offset_s is None:
        return None
    for row in holdout_rows:
        if row.get("family") == family and row.get("offset_s") == offset_s:
            if row.get("accuracy") is None:
                return None
            return {
                "family": family,
                "offset_s": offset_s,
                "accuracy": float(row["accuracy"]),
                "n_scored": row.get("n_scored"),
                "coverage": row.get("coverage"),
                "wilson_lo": row.get("wilson_lo"),
                "wilson_hi": row.get("wilson_hi"),
            }
    return None


def enrich_hero_card(card: dict | None, sweep_holdout: list[dict] | None = None) -> dict | None:
    """Attach hero_* fields to a preview card dict (mutates a shallow copy)."""
    if not card:
        return card
    out = dict(card)
    conf = confidence_from_p(out.get("p_yes"), out.get("pred_yes"))
    out["hero_direction"] = conf["direction"]
    out["hero_confidence_pct"] = conf["confidence_pct"]
    out["hero_confidence_label"] = conf["label"]
    fe, mode = consistent_forecast_end(out.get("pred_yes"), out.get("S_t"), out.get("forecast_end"))
    out["hero_forecast_end"] = fe
    out["hero_forecast_end_mode"] = mode
    if out.get("logret_1") is None and out.get("x"):
        try:
            out["logret_1"] = float(out["x"][0])
        except (TypeError, ValueError, IndexError):
            pass
    if out.get("time_left_s") is None and out.get("time_left") is not None:
        out["time_left_s"] = out.get("time_left")
    out["hero_why"] = why_sentences(out)
    hist = historical_accuracy_at(sweep_holdout, out.get("family"), out.get("decision_offset_s"))
    out["hero_historical"] = hist
    if hist and hist.get("n_scored"):
        n = int(hist["n_scored"])
        # accuracy * n may not be exact integer; prefer explicit n_correct if present
        if hist.get("n_correct") is not None:
            k = int(hist["n_correct"])
        else:
            k = int(round(float(hist["accuracy"]) * n))
        out["hero_historical_summary"] = format_correct_summary(k, n)
    else:
        out["hero_historical_summary"] = None
    change = None
    if out.get("S_t") is not None and out.get("R_t") is not None:
        change = float(out["R_t"]) - float(out["S_t"])
    out["hero_change"] = change
    return out
