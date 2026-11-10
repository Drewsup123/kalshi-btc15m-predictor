from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.asof import opening_ref, last10
from kxbtc15m.v3.clock import t_star

OPEN = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
TSTAR = t_star(OPEN)

PRIOR = {
    "ticker": "PREV",
    "open_time": "2026-11-05T23:45:00Z",
    "close_time": "2026-11-06T00:00:00Z",
    "settlement_ts": "2026-11-06T00:00:07Z",
    "expiration_value": "100.0",
    "floor_strike": 99.0,
    "result": "yes",
    "status": "finalized",
}
CUR = {
    "ticker": "CUR",
    "open_time": "2026-11-06T00:00:00Z",
    "close_time": "2026-11-06T00:15:00Z",
    "floor_strike": 100.0,
    "expiration_value": "101.0",
    "result": "yes",
}


def test_replay_uses_prior_print_not_eventual_floor():
    s, src, skip = opening_ref(CUR, [PRIOR], TSTAR, availability="historical_replay")
    assert skip is None
    assert s == 100.0
    assert src == "prior_expiration_value"
    assert s != float(CUR["expiration_value"])


def test_no_prior_print_skips_even_if_eventual_floor_present():
    s, src, skip = opening_ref(CUR, [], TSTAR, availability="historical_replay")
    assert skip == "insufficient_opening_ref"
    assert s is None


def test_settlement_after_tstar_not_eligible_for_last10():
    late = dict(PRIOR, settlement_ts="2026-11-06T00:00:45Z", result="no")
    got = last10([late], TSTAR, availability="historical_replay")
    assert got["used"] == 0


def test_live_late_response_cannot_supply_st():
    s, src, skip = opening_ref(
        CUR,
        [PRIOR],
        TSTAR,
        availability="observed_live",
        observation_at=TSTAR + timedelta(seconds=5),
        request_started_at=TSTAR - timedelta(seconds=5),
    )
    assert skip == "insufficient_opening_ref"
