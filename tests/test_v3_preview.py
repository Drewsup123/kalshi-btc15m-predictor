from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.preview import denver_stamp, _elapsed_offset, _latest_print
from kxbtc15m.v3.screen import render_html


def test_denver_format_has_zone_and_year_first():
    stamp = denver_stamp("2026-11-10T07:15:00Z")
    assert stamp.startswith("2026-11-10")
    assert "MST" in stamp or "MDT" in stamp or "GMT" in stamp or "America" in stamp or "M" in stamp


def test_elapsed_offset_clamps_to_grid():
    market = {
        "open_time": "2026-11-10T07:15:00Z",
        "close_time": "2026-11-10T07:30:00Z",
    }
    now = datetime(2026, 11, 10, 7, 14, tzinfo=timezone.utc)
    assert _elapsed_offset(market, now) == 0
    now = datetime(2026, 11, 10, 7, 20, tzinfo=timezone.utc)
    assert _elapsed_offset(market, now) == 300
    now = datetime(2026, 11, 10, 7, 29, tzinfo=timezone.utc)
    assert _elapsed_offset(market, now) == 840


def test_latest_print_prefers_settled_prior_not_coinbase_when_eligible():
    t_dec = datetime(2026, 11, 10, 7, 15, 30, tzinfo=timezone.utc)
    priors = [
        {
            "settlement_ts": "2026-11-10T07:15:03Z",
            "result": "yes",
            "expiration_value": "111.0",
        }
    ]
    val, src = _latest_print(priors, t_dec, coinbase_last=99.0)
    assert val == 111.0
    assert src == "prior_expiration_value"
    late = [
        {
            "settlement_ts": "2026-11-10T07:16:00Z",
            "result": "yes",
            "expiration_value": "111.0",
        }
    ]
    val2, src2 = _latest_print(late, t_dec, coinbase_last=99.0)
    assert val2 == 99.0
    assert src2 == "coinbase_last_print"


def test_screen_preview_card_labeled():
    metrics = {
        "availability": "historical_replay",
        "replay_assumption": "prior_print_after_settlement_ts",
        "dataset_asof": "2026-11-10T00:00:00Z",
        "run_generated_at": "2026-11-10T08:00:00Z",
        "model_version": "v3-test",
        "calibration": "uncalibrated",
        "n_train": 1,
        "n_validation": 1,
        "n_holdout": 1,
        "n_skipped": 0,
        "n_inventory_scored_universe": 3,
        "holdout": {},
        "aspiration": {"low": 0.75, "high": 0.9},
        "preview": {
            "next": {
                "ticker": "KXBTC15M-26NOV100245-45",
                "open_denver": "2026-11-10 00:45 MST",
                "close_denver": "2026-11-10 01:00 MST",
                "S_t": 74000,
                "pred_yes": "yes",
                "p_yes": 0.61,
                "forecast_end": 74100,
                "label": "PREVIEW / pre-open",
            }
        },
        "sweep": {
            "holdout_label": "holdout_previously_viewed",
            "n_variants_tried": 12,
            "target_accuracy": 0.75,
        },
    }
    html = render_html(metrics, [])
    assert "PREVIEW / pre-open" in html
    assert "KXBTC15M-26NOV100245-45" in html
    assert "previously viewed" in html.lower() or "previously_viewed" in html
