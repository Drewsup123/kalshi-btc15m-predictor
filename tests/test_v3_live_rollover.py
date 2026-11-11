"""Market rollover helpers for live preview."""

from datetime import datetime, timezone

from kxbtc15m.v3.preview import _elapsed_offset, select_current_market


def test_select_current_market_picks_latest_open():
    markets = [
        {
            "ticker": "OLD",
            "open_time": "2026-11-11T18:00:00Z",
            "close_time": "2026-11-11T18:15:00Z",
            "status": "open",
        },
        {
            "ticker": "NEW",
            "open_time": "2026-11-11T18:15:00Z",
            "close_time": "2026-11-11T18:30:00Z",
            "status": "open",
        },
    ]
    now = datetime(2026, 11, 11, 18, 16, tzinfo=timezone.utc)
    cur = select_current_market(markets, now)
    assert cur["ticker"] == "NEW"


def test_rollover_offset_resets_after_new_open():
    old = {"open_time": "2026-11-11T18:00:00Z", "close_time": "2026-11-11T18:15:00Z"}
    new = {"open_time": "2026-11-11T18:15:00Z", "close_time": "2026-11-11T18:30:00Z"}
    late_in_old = datetime(2026, 11, 11, 18, 14, tzinfo=timezone.utc)
    early_in_new = datetime(2026, 11, 11, 18, 15, 40, tzinfo=timezone.utc)
    assert _elapsed_offset(old, late_in_old) == 840
    assert _elapsed_offset(new, early_in_new) == 30
