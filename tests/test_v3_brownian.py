from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.clock import decision_time
from kxbtc15m.v3.brownian import norm_cdf, p_yes_brownian, realized_sigma


def test_decision_time_offsets():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    assert decision_time(open_t, 30) == open_t + timedelta(seconds=30)
    assert decision_time(open_t, 840) == open_t + timedelta(minutes=14)
    assert decision_time(open_t, 0) == open_t


def test_brownian_sure_when_far_and_tau_short():
    p, z = p_yes_brownian(r_t=101.0, s_t=100.0, sigma=0.0004, tau_minutes=1.0)
    assert p > 0.99
    assert z > 0
    p_no, z_no = p_yes_brownian(r_t=99.0, s_t=100.0, sigma=0.0004, tau_minutes=1.0)
    assert p_no < 0.01
    assert z_no < 0


def test_brownian_half_when_at_strike():
    p0, z0 = p_yes_brownian(r_t=100.0, s_t=100.0, sigma=0.001, tau_minutes=10.0)
    assert abs(p0 - 0.5) < 1e-9
    assert abs(z0) < 1e-12


def test_norm_cdf_symmetric():
    assert abs(norm_cdf(0.0) - 0.5) < 1e-12
    assert abs(norm_cdf(1.0) + norm_cdf(-1.0) - 1.0) < 1e-12


def test_realized_sigma_positive():
    closes = [100.0, 100.1, 99.9, 100.2, 100.0]
    sig = realized_sigma(closes, 4)
    assert sig is not None and sig > 0
