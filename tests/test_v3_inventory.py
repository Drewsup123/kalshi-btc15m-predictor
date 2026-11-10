from kxbtc15m.v3.inventory import score_universe, grid_holes, dedup_by_ticker


def test_excludes_void_and_missing_prints():
    rows = [
        {
            "ticker": "A",
            "status": "finalized",
            "result": "yes",
            "floor_strike": 1,
            "expiration_value": "2",
            "strike_type": "greater_or_equal",
            "close_time": "2026-01-10T00:15:00Z",
            "open_time": "2026-01-10T00:00:00Z",
        },
        {
            "ticker": "B",
            "status": "finalized",
            "result": "",
            "floor_strike": 1,
            "expiration_value": "2",
            "strike_type": "greater_or_equal",
            "close_time": "2026-01-10T00:30:00Z",
            "open_time": "2026-01-10T00:15:00Z",
        },
        {
            "ticker": "C",
            "status": "finalized",
            "result": "no",
            "floor_strike": None,
            "expiration_value": "2",
            "strike_type": "greater_or_equal",
            "close_time": "2026-01-10T00:45:00Z",
            "open_time": "2026-01-10T00:30:00Z",
        },
    ]
    scored, excluded = score_universe(rows)
    assert [r["ticker"] for r in scored] == ["A"]
    assert {e["ticker"] for e in excluded} == {"B", "C"}


def test_dedup_and_grid_hole():
    rows = [
        {
            "ticker": "A",
            "close_time": "2026-01-10T00:15:00Z",
            "open_time": "2026-01-10T00:00:00Z",
            "status": "finalized",
            "result": "yes",
            "floor_strike": 1,
            "expiration_value": "1.1",
            "strike_type": "greater_or_equal",
        },
        {
            "ticker": "A",
            "close_time": "2026-01-10T00:15:00Z",
            "open_time": "2026-01-10T00:00:00Z",
            "status": "finalized",
            "result": "yes",
            "floor_strike": 1,
            "expiration_value": "1.1",
            "strike_type": "greater_or_equal",
        },
        {
            "ticker": "C",
            "close_time": "2026-01-10T00:45:00Z",
            "open_time": "2026-01-10T00:30:00Z",
            "status": "finalized",
            "result": "no",
            "floor_strike": 1,
            "expiration_value": "0.9",
            "strike_type": "greater_or_equal",
        },
    ]
    scored, _ = score_universe(dedup_by_ticker(rows))
    holes = grid_holes(scored)
    assert any(h.endswith("00:30:00Z") for h in holes)
