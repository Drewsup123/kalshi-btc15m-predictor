"""Named controls. Not hidden inside kNN."""

from __future__ import annotations

from kxbtc15m.v3.asof import last10_majority


def majority_side(labels: list[str]) -> str:
    yes = sum(1 for x in labels if str(x).lower() == "yes")
    no = sum(1 for x in labels if str(x).lower() == "no")
    if yes == no:
        return "yes"  # equality-style fallback only if train is split; rare
    return "yes" if yes > no else "no"


def no_change() -> tuple[str, float]:
    """ŷ_log=0 → forecast_end=S_t → YES by official equality."""
    return "yes", 0.0


def last_price_side(r_t: float, s_t: float) -> str:
    return "yes" if r_t >= s_t else "no"


def last10_side(stats: dict) -> str | None:
    return last10_majority(stats)
