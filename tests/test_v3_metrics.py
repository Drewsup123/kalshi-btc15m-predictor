from kxbtc15m.v3.metrics import score_table, empty_metrics


def test_skip_not_error():
    rows = [
        {
            "pred_yes": "yes",
            "result": "yes",
            "skip_reason": None,
            "forecast_end": 101,
            "expiration_value": 100,
        },
        {
            "pred_yes": None,
            "result": "no",
            "skip_reason": "insufficient_opening_ref",
            "forecast_end": None,
            "expiration_value": 100,
        },
    ]
    m = score_table(rows)
    assert m["n_scored"] == 1
    assert m["accuracy"] == 1.0
    assert m["coverage"] == 0.5
    assert m["n_skip"] == 1


def test_empty_has_no_accuracy_number():
    m = empty_metrics()
    assert m["accuracy"] is None
