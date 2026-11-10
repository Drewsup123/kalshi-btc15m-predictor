from datetime import datetime, timezone, timedelta

import numpy as np

from kxbtc15m.v3.models import fit_logistic, fit_ridge, knn_predict, StandardScaler
from kxbtc15m.v3.controls import majority_side, no_change, last_price_side


def test_scaler_train_only():
    s = StandardScaler().fit(np.array([[0.0], [2.0]]))
    assert abs(s.mean_[0] - 1.0) < 1e-9
    z = s.transform(np.array([[4.0]]))
    assert abs(z[0, 0] - 3.0) < 1e-6


def test_logistic_separates():
    X = np.vstack([np.zeros((20, 2)), np.ones((20, 2))])
    y = np.array([0] * 20 + [1] * 20)
    m = fit_logistic(X, y, l2=1.0)
    p = m.predict_proba(np.array([[1.0, 1.0]]))[0]
    assert p > 0.5


def test_ridge_zero_when_y_zero():
    X = np.random.RandomState(0).randn(30, 3)
    y = np.zeros(30)
    m = fit_ridge(X, y, l2=1.0)
    assert abs(m.predict(X).mean()) < 1e-6


def test_knn_purges_nearby_window():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    library = [
        {"x": np.zeros(2), "label": 1, "open": t0, "y_log": 0.01},
        {"x": np.ones(2), "label": 0, "open": t0 - timedelta(days=2), "y_log": -0.01},
    ]
    pred, p, yhat = knn_predict(
        np.zeros(2),
        t_star=t0 + timedelta(minutes=15, seconds=30),
        library=library,
        k=25,
    )
    assert pred == 0


def test_controls():
    assert majority_side(["yes", "yes", "no"]) == "yes"
    assert no_change() == ("yes", 0.0)
    assert last_price_side(101.0, 100.0) == "yes"
    assert last_price_side(99.0, 100.0) == "no"
