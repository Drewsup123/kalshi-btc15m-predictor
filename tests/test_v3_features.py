from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.candles import filter_completed
from kxbtc15m.v3.features import FEATURE_NAMES, build_features
from kxbtc15m.v3.clock import t_star

OPEN = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
TSTAR = t_star(OPEN)


def bars(n, end=OPEN):
    out = []
    for i in range(n):
        start = end - timedelta(minutes=n - i)
        out.append(
            {
                "start": start,
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100 + 0.01 * i,
                "volume": 1.0,
            }
        )
    return out


def test_drops_bar_ending_after_tstar():
    illegal = {"start": OPEN, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    kept = filter_completed(bars(2) + [illegal], TSTAR)
    assert illegal not in kept
    assert all(b["start"] + timedelta(seconds=60) <= TSTAR for b in kept)


def test_feature_names_have_no_usd_residual():
    assert not any("dollar" in n or n.endswith("_usd") for n in FEATURE_NAMES)
    assert "last10_median_logret" in FEATURE_NAMES


def test_insufficient_history_without_16_bars():
    vec, meta, skip = build_features(
        bars(5),
        last10={"used": 0, "yes": 0, "no": 0, "median_logret": 0.0},
        t_star=TSTAR,
    )
    assert skip == "missing_underlying"
    assert vec is None
