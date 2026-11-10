"""Numpy L2 logistic, Ridge, purged kNN. Train-only scalers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from kxbtc15m.v3 import KNN_K, LOOKBACK_BARS


class StandardScaler:
    def __init__(self):
        self.mean_ = None
        self.scale_ = None

    def fit(self, X: np.ndarray) -> "StandardScaler":
        X = np.asarray(X, dtype=float)
        self.mean_ = X.mean(axis=0)
        std = X.std(axis=0, ddof=0)
        std[std < 1e-12] = 1.0
        self.scale_ = std
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        return (X - self.mean_) / self.scale_


@dataclass
class LinearModel:
    coef: np.ndarray  # includes intercept at [0]
    kind: str

    def predict(self, X: np.ndarray) -> np.ndarray:
        Xb = np.column_stack([np.ones(len(X)), np.asarray(X, dtype=float)])
        return Xb @ self.coef

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = np.clip(self.predict(X), -30, 30)
        return 1.0 / (1.0 + np.exp(-z))


def fit_ridge(X: np.ndarray, y: np.ndarray, l2: float = 1.0) -> LinearModel:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    Xb = np.column_stack([np.ones(n), X])
    xtx = Xb.T @ Xb
    reg = np.eye(p + 1) * l2
    reg[0, 0] = 0.0
    beta = np.linalg.solve(xtx + reg + 1e-8 * np.eye(p + 1), Xb.T @ y)
    return LinearModel(beta, "ridge")


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, max_iter: int = 40) -> LinearModel:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    Xb = np.column_stack([np.ones(n), X])
    w = np.zeros(p + 1)
    for _ in range(max_iter):
        z = np.clip(Xb @ w, -20, 20)
        p_hat = 1.0 / (1.0 + np.exp(-z))
        W = np.clip(p_hat * (1.0 - p_hat), 1e-6, None)
        adj = z + (y - p_hat) / W
        H = Xb.T @ (W[:, None] * Xb)
        reg = np.eye(p + 1) * l2
        reg[0, 0] = 0.0
        H = H + reg
        rhs = Xb.T @ (W * adj)
        w_new = np.linalg.solve(H + 1e-8 * np.eye(p + 1), rhs)
        if np.max(np.abs(w_new - w)) < 1e-7:
            w = w_new
            break
        w = w_new
    return LinearModel(w, "logistic")


def knn_predict(
    x: np.ndarray,
    t_star: datetime,
    library: list[dict],
    k: int = KNN_K,
) -> tuple[int | None, float | None, float | None]:
    lo = t_star - timedelta(minutes=LOOKBACK_BARS)
    eligible = [row for row in library if not (lo < row["open"] <= t_star)]
    if not eligible:
        return None, None, None
    x = np.asarray(x, dtype=float)
    mat = np.asarray([row["x"] for row in eligible], dtype=float)
    dists = np.linalg.norm(mat - x, axis=1)
    take = min(k, len(eligible))
    idx = np.argsort(dists)[:take]
    picked = [eligible[i] for i in idx]
    votes = [int(p["label"]) for p in picked]
    pred = 1 if sum(votes) > len(votes) / 2 else 0
    p_yes = sum(votes) / len(votes)
    yhat = float(np.median([p["y_log"] for p in picked]))
    return pred, p_yes, yhat
