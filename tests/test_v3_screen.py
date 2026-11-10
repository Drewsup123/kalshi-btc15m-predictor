from kxbtc15m.v3.screen import render_html


def test_untrained_has_no_fake_accuracy():
    text = render_html(None)
    assert "not trained" in text
    assert "80.0%" not in text
    assert "accuracy" not in text.lower() or "no accuracy" in text.lower()


def test_live_panel_unavailable_without_observed_snapshot():
    metrics = {
        "availability": "historical_replay",
        "replay_assumption": "prior_print_after_settlement_ts",
        "dataset_asof": "2026-11-10T00:00:00Z",
        "run_generated_at": "2026-11-10T06:00:00Z",
        "model_version": "v3-test",
        "calibration": "uncalibrated",
        "n_train": 1,
        "n_validation": 1,
        "n_holdout": 1,
        "n_skipped": 0,
        "n_inventory_scored_universe": 3,
        "holdout": {"A_logistic": {"accuracy": 0.5, "wilson_lo": 0.1, "wilson_hi": 0.9, "coverage": 1, "mae": 10, "n_scored": 1}},
        "aspiration": {"low": 0.8, "high": 0.9},
    }
    html = render_html(metrics, [{"availability": "historical_replay", "pred_yes": "yes", "split": "holdout", "ticker": "T"}])
    assert "unavailable" in html
    assert "prediction_asof" in html
    assert "run_generated_at" in html
    assert "dataset_asof" in html
    assert "historical_replay" in html
