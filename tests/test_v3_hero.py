"""Hero confidence, why-text, consistency, and % formatting."""

from kxbtc15m.v3.hero import (
    confidence_from_p,
    consistent_forecast_end,
    end_price_agrees_with_direction,
    format_correct_summary,
    historical_accuracy_at,
    why_sentences,
)


def test_confidence_low_medium_high_thresholds():
    low = confidence_from_p(0.52, "yes")
    assert low["confidence_pct"] == 52
    assert low["label"] == "Low"
    assert low["direction"] == "UP"

    med = confidence_from_p(0.40, "no")
    assert med["confidence_pct"] == 60
    assert med["label"] == "Medium"
    assert med["direction"] == "DOWN"

    high = confidence_from_p(0.72, "yes")
    assert high["confidence_pct"] == 72
    assert high["label"] == "High"

    missing = confidence_from_p(None, "yes")
    assert missing["confidence_pct"] is None
    assert missing["label"] is None


def test_why_text_uses_change_time_and_momentum():
    text = why_sentences(
        {
            "S_t": 100_000.0,
            "R_t": 100_040.0,
            "time_left_s": 9 * 60 + 20,
            "logret_1": -0.0012,
        }
    )
    assert "40" in text
    assert "above" in text.lower()
    assert "9 minute" in text.lower()
    assert "momentum" in text.lower() and "down" in text.lower()


def test_why_text_omits_invented_momentum_when_flat():
    text = why_sentences({"S_t": 100.0, "R_t": 99.0, "time_left_s": 120, "logret_1": 0.0})
    assert "below" in text.lower()
    assert "momentum" not in text.lower()


def test_end_price_consistency_agree_and_hide():
    assert end_price_agrees_with_direction("yes", 100.0, 105.0) is True
    assert end_price_agrees_with_direction("no", 100.0, 95.0) is True
    assert end_price_agrees_with_direction("yes", 100.0, 95.0) is False
    assert end_price_agrees_with_direction("no", 100.0, 105.0) is False

    shown, mode = consistent_forecast_end("yes", 100.0, 105.0)
    assert shown == 105.0 and mode == "show"
    hidden, mode2 = consistent_forecast_end("no", 100.0, 105.0)
    assert hidden is None and mode2 == "hide"


def test_format_correct_summary_and_zero():
    assert format_correct_summary(7, 12) == "7 of 12 correct (58%)"
    assert format_correct_summary(1, 1) == "1 of 1 correct (100%)"
    assert format_correct_summary(0, 0) is None


def test_historical_accuracy_lookup_by_family_offset():
    rows = [
        {"family": "D_brownian_16", "offset_s": 300, "accuracy": 0.71, "n_scored": 100, "coverage": 1.0},
        {"family": "C_lastprice", "offset_s": 300, "accuracy": 0.70, "n_scored": 100, "coverage": 1.0},
    ]
    hit = historical_accuracy_at(rows, "D_brownian_16", 300)
    assert hit["accuracy"] == 0.71
    assert hit["n_scored"] == 100
    assert historical_accuracy_at(rows, "A_logistic_z", 999) is None
