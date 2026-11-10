from datetime import datetime, timezone, timedelta

from kxbtc15m.v3.clock import t_star, deadline, t_pub_sim, time_left_seconds


def test_t_star_is_open_plus_30s():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    assert t_star(open_t) == open_t + timedelta(seconds=30)
    assert deadline(open_t) == open_t + timedelta(seconds=60)


def test_t_pub_sim_clamped_and_miss_after_deadline():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    assert t_pub_sim(open_t, open_t + timedelta(seconds=45)) == open_t + timedelta(seconds=45)
    assert t_pub_sim(open_t, open_t + timedelta(seconds=61)) is None


def test_time_left_uses_close_minus_tstar():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    close_t = datetime(2026, 11, 6, 0, 15, tzinfo=timezone.utc)
    assert time_left_seconds(open_t, close_t) == 14.5 * 60


def test_run_generated_at_is_not_t_pub():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    run = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)
    assert t_pub_sim(open_t, t_star(open_t)) != run
