from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.asof import opening_ref, last10
from kxbtc15m.v3.candles import filter_completed
from kxbtc15m.v3.clock import t_star
from kxbtc15m.v3.metrics import permutation_disclosure

OPEN = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
TSTAR = t_star(OPEN)


def test_permutation_helper_does_not_accept_holdout_tag():
    try:
        permutation_disclosure(
            [{"split": "holdout", "pred_yes": "yes", "result": "no"}],
            split_allowed=("validation",),
        )
        raise AssertionError("must refuse holdout")
    except ValueError:
        pass


def test_future_bar_dropped():
    future = {
        "start": OPEN,
        "open": 1,
        "high": 1,
        "low": 1,
        "close": 1,
        "volume": 1,
    }
    kept = filter_completed([future], TSTAR)
    assert kept == []


def test_eventual_floor_not_used_without_prior():
    cur = {
        "ticker": "CUR",
        "open_time": "2026-11-06T00:00:00Z",
        "floor_strike": 999.0,
        "expiration_value": "1000",
        "result": "yes",
    }
    s, src, skip = opening_ref(cur, [], TSTAR)
    assert skip == "insufficient_opening_ref"
    assert s is None


def test_last10_ignores_close_before_open_if_unsettled():
    late = {
        "ticker": "PREV",
        "close_time": "2026-11-06T00:00:00Z",
        "settlement_ts": "2026-11-06T00:00:45Z",
        "expiration_value": "1",
        "floor_strike": 1,
        "result": "no",
        "status": "finalized",
    }
    assert last10([late], TSTAR)["used"] == 0


def test_live_request_before_tstar_response_after_unusable():
    cur = {"ticker": "CUR", "open_time": "2026-11-06T00:00:00Z", "floor_strike": 1, "expiration_value": "2"}
    prior = {
        "ticker": "P",
        "settlement_ts": "2026-11-06T00:00:07Z",
        "expiration_value": "100",
        "floor_strike": 99,
        "result": "yes",
    }
    s, src, skip = opening_ref(
        cur,
        [prior],
        TSTAR,
        availability="observed_live",
        observation_at=TSTAR + timedelta(seconds=1),
        request_started_at=TSTAR - timedelta(seconds=10),
    )
    assert skip == "insufficient_opening_ref"
