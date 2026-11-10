from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.clock import decision_time
from kxbtc15m.v3.evaluate import build_replay_rows
from kxbtc15m.v3.metrics import score_table
from kxbtc15m.v3.sweep import apply_family, apply_selective, select_best, TARGET_ACC


def _bars(start, n, drift=0.0):
    price = 100.0
    out = []
    t = start
    for i in range(n):
        price = max(10.0, price + drift)
        out.append(
            {
                "start": t,
                "open": price,
                "high": price + 0.05,
                "low": price - 0.05,
                "close": price,
                "volume": 1.0,
            }
        )
        t += timedelta(minutes=1)
    return out


def _markets(n, start):
    floor = 100.0
    rows = []
    for i in range(n):
        open_t = start + timedelta(minutes=15 * i)
        close_t = open_t + timedelta(minutes=15)
        expv = floor + 1.0
        rows.append(
            {
                "ticker": f"KXBTC15M-{i:04d}",
                "status": "finalized",
                "result": "yes" if expv >= floor else "no",
                "floor_strike": floor,
                "expiration_value": str(expv),
                "strike_type": "greater_or_equal",
                "open_time": open_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "close_time": close_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "settlement_ts": (close_t + timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        floor = expv
    return rows


def test_later_offset_may_use_current_window_bar():
    start = datetime(2026, 3, 1, 4, 0, tzinfo=timezone.utc)
    markets = _markets(4, start)
    bars = _bars(start - timedelta(hours=4), 500, drift=0.02)
    early = build_replay_rows(markets, bars, offset_seconds=30)
    late = build_replay_rows(markets, bars, offset_seconds=840)
    row_e = next(r for r in early if r["R_t"] is not None)
    row_l = next(r for r in late if r["ticker"] == row_e["ticker"] and r["R_t"] is not None)
    open_t = datetime.fromisoformat(row_e["open_time"].replace("Z", "+00:00"))
    assert row_e["decision_offset_s"] == 30
    assert decision_time(open_t, 840) == datetime.fromisoformat(row_l["prediction_asof"].replace("Z", "+00:00"))
    assert row_l["R_t"] != row_e["R_t"] or row_l["tau_minutes"] < row_e["tau_minutes"]
    assert row_l["tau_minutes"] <= 1.01


def test_selective_reports_coverage():
    rows = [
        {"pred_yes": "yes", "result": "yes", "p_yes": 0.9, "skip_reason": None},
        {"pred_yes": "no", "result": "no", "p_yes": 0.52, "skip_reason": None},
        {"pred_yes": "yes", "result": "no", "p_yes": 0.51, "skip_reason": None},
    ]
    sel = apply_selective(rows, 0.2)
    table = score_table(sel)
    assert table["n_scored"] == 1
    assert table["coverage"] == 1 / 3
    assert table["accuracy"] == 1.0


def test_select_best_prefers_coverage_at_75():
    rows = [
        {"id": "hi_cov", "accuracy": 0.76, "coverage": 0.9},
        {"id": "hi_acc", "accuracy": 0.95, "coverage": 0.1},
        {"id": "low", "accuracy": 0.55, "coverage": 1.0},
    ]
    chosen = select_best(rows)
    assert chosen["chosen"]["id"] == "hi_cov"
    assert chosen["rule"] == "max_coverage_among_wf_ge_75"
    assert TARGET_ACC == 0.75


def test_lastprice_applies():
    rows = [
        {
            "S_t": 100.0,
            "R_t": 101.0,
            "result": "yes",
            "skip_reason": None,
            "x": [0.0] * 21,
            "last10": {"used": 10, "yes": 6, "no": 4, "median_logret": 0.0},
        }
    ]
    pred = apply_family(rows, "C_lastprice", {})
    assert pred[0]["pred_yes"] == "yes"
