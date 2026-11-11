"""Screen hero layout, Details section, and % correct lines."""

from kxbtc15m.v3.hero import enrich_hero_card
from kxbtc15m.v3.screen import render_html


def _base_metrics():
    return {
        "availability": "historical_replay",
        "replay_assumption": "prior_print_after_settlement_ts",
        "dataset_asof": "2026-11-10T00:00:00Z",
        "run_generated_at": "2026-11-11T08:00:00Z",
        "model_version": "v3-test",
        "calibration": "uncalibrated",
        "n_train": 10,
        "n_validation": 2,
        "n_holdout": 3,
        "n_skipped": 0,
        "n_inventory_scored_universe": 15,
        "holdout": {
            "A_logistic": {
                "accuracy": 0.5,
                "wilson_lo": 0.1,
                "wilson_hi": 0.9,
                "coverage": 1,
                "mae": 10,
                "n_scored": 2,
            }
        },
        "aspiration": {"low": 0.75, "high": 0.9},
    }


def test_hero_shows_up_confidence_why_and_hides_inconsistent_end():
    metrics = _base_metrics()
    card = enrich_hero_card(
        {
            "ticker": "KXBTC15M-LIVE",
            "open_denver": "2026-11-11 12:00 MST",
            "close_denver": "2026-11-11 12:15 MST",
            "open_time": "2026-11-11T19:00:00Z",
            "close_time": "2026-11-11T19:15:00Z",
            "S_t": 100000.0,
            "R_t": 100040.0,
            "pred_yes": "no",
            "p_yes": 0.38,
            "forecast_end": 100040.0,  # disagrees with NO
            "family": "D_brownian_16",
            "decision_offset_s": 300,
            "time_left_s": 540,
            "logret_1": -0.001,
        },
        [{"family": "D_brownian_16", "offset_s": 300, "accuracy": 0.71, "n_scored": 100, "coverage": 1.0}],
    )
    metrics["preview"] = {"current": card, "stale": False, "live_track": {"summary": {
        "all_time": {"summary": "2 of 3 correct (67%)"},
        "today": {"summary": "1 of 2 correct (50%)"},
    }}}
    html = render_html(metrics, [])
    assert 'id="hero"' in html
    assert "DOWN" in html
    assert "Medium" in html or "62%" in html
    assert "above the open" in html.lower() or "40" in html
    assert "Model end (consistent)" not in html  # hidden when inconsistent
    assert "Details" in html
    assert "Guessed correctly" in html
    assert "2 of 3 correct (67%)" in html
    assert "Recent calls" in html


def test_hero_shows_consistent_end_price_when_aligned():
    metrics = _base_metrics()
    card = enrich_hero_card(
        {
            "ticker": "KXBTC15M-LIVE",
            "open_denver": "2026-11-11 12:00 MST",
            "close_denver": "2026-11-11 12:15 MST",
            "close_time": "2026-11-11T19:15:00Z",
            "S_t": 100.0,
            "R_t": 105.0,
            "pred_yes": "yes",
            "p_yes": 0.7,
            "forecast_end": 105.0,
            "family": "C_lastprice",
            "decision_offset_s": 60,
            "time_left_s": 600,
        }
    )
    metrics["preview"] = {"current": card}
    html = render_html(metrics, [])
    assert "UP" in html
    assert "Model end (consistent)" in html
    assert "105.00" in html


def test_holdout_table_includes_percent_correct():
    metrics = _base_metrics()
    preds = [
        {
            "split": "holdout",
            "ticker": "A",
            "prediction_asof": "t",
            "pred_yes": "yes",
            "result": "yes",
            "availability": "historical_replay",
            "S_t": 1,
            "forecast_end": 1,
            "expiration_value": 1,
        },
        {
            "split": "holdout",
            "ticker": "B",
            "prediction_asof": "t",
            "pred_yes": "yes",
            "result": "no",
            "availability": "historical_replay",
            "S_t": 1,
            "forecast_end": 1,
            "expiration_value": 1,
        },
    ]
    html = render_html(metrics, preds)
    assert "1 of 2 correct (50%)" in html
    assert "Holdout markets (first 200)" in html
