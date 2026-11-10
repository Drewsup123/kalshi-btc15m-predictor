from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.split import chronological_split, walkforward_slices


def test_70_15_15_order_preserved():
    rows = [
        {"close_time": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i)}
        for i in range(100)
    ]
    tr, va, ho = chronological_split(rows)
    assert len(tr) == 70 and len(va) == 15 and len(ho) == 15
    assert tr[-1]["close_time"] < va[0]["close_time"] < ho[0]["close_time"]


def test_embargo_gap():
    rows = [
        {"close_time": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i)}
        for i in range(2000)
    ]
    slices = walkforward_slices(rows[:1700], slice_days=7)
    assert slices
    for train, test in slices:
        gap = test[0]["close_time"] - train[-1]["close_time"]
        assert gap >= timedelta(minutes=96 + 15)
