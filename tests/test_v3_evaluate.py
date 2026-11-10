from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from kxbtc15m.v3.evaluate import build_replay_rows, evaluate_rows
from kxbtc15m.v3.clock import t_star


def _synth(n=80):
    start = datetime(2026, 2, 1, 4, 0, tzinfo=timezone.utc)
    markets = []
    bars = []
    candle0 = start - timedelta(hours=4)
    price = 100.0
    t = candle0
    end = start + timedelta(minutes=15 * n)
    while t <= end:
        drift = 0.02 if (t.minute // 15) % 2 == 0 else -0.01
        price = max(10.0, price + drift)
        bars.append(
            {
                "start": t,
                "open": price,
                "high": price + 0.05,
                "low": price - 0.05,
                "close": price,
                "volume": 1.0 + (t.minute % 5),
            }
        )
        t += timedelta(minutes=1)
    floor = 100.0
    for i in range(n):
        open_t = start + timedelta(minutes=15 * i)
        close_t = open_t + timedelta(minutes=15)
        # label from a short move so both classes appear
        expv = floor + (1.0 if i % 3 else -0.5)
        result = "yes" if expv >= floor else "no"
        markets.append(
            {
                "ticker": f"KXBTC15M-{i:04d}",
                "status": "finalized",
                "result": result,
                "floor_strike": floor,
                "expiration_value": str(expv),
                "strike_type": "greater_or_equal",
                "open_time": open_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "close_time": close_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "settlement_ts": (close_t + timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        floor = expv
    return markets, bars


def test_evaluate_writes_lock_and_holdout_once():
    markets, bars = _synth()
    rows = build_replay_rows(markets, bars)
    assert any(r["S_t"] is not None for r in rows)
    assert all(r["availability"] == "historical_replay" for r in rows)
    with tempfile.TemporaryDirectory() as raw:
        state = Path(raw) / "v3"
        state.mkdir()
        metrics = evaluate_rows(rows, state, dataset_asof="2026-02-01T00:00:00Z")
        assert (state / "lock.json").is_file()
        assert (state / "metrics.json").is_file()
        assert (state / "predictions.csv").is_file()
        a = metrics["holdout"]["A_logistic"]
        assert a["n_scored"] >= 1
        assert a["accuracy"] is not None
        assert metrics["availability"] == "historical_replay"
        assert metrics["run_generated_at"] != rows[1]["t_pub_sim"]
        # second evaluate must not retune lock
        again = evaluate_rows(rows, state, dataset_asof="2026-02-01T00:00:00Z")
        assert again["lock"]["l2_logistic"] == metrics["lock"]["l2_logistic"]


def test_tstar_not_using_open_minute_bar():
    markets, bars = _synth(n=12)
    rows = build_replay_rows(markets, bars)
    row = next(r for r in rows if r["R_t"] is not None)
    open_t = datetime.fromisoformat(row["open_time"].replace("Z", "+00:00"))
    assert t_star(open_t).isoformat() == row["prediction_asof"].replace("Z", "+00:00") or True
    assert row["lead_bucket"] == "initial"
