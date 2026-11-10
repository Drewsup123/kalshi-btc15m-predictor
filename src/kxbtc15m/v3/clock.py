"""Frozen first-minute decision clock. t* = open+30s; deadline = open+60s."""

from __future__ import annotations

from datetime import datetime, timedelta

from kxbtc15m.clock import parse_utc


def t_star(open_time: datetime | str) -> datetime:
    return parse_utc(open_time) + timedelta(seconds=30)


def decision_time(open_time: datetime | str, offset_seconds: float) -> datetime:
    """Frozen decision instant. offset_seconds=30 is Phase-1 t*; 0 is pre-open."""
    return parse_utc(open_time) + timedelta(seconds=float(offset_seconds))


def deadline(open_time: datetime | str) -> datetime:
    return parse_utc(open_time) + timedelta(seconds=60)


def t_pub_sim(open_time: datetime | str, emit_at: datetime | str) -> datetime | None:
    """Simulated publish. None → missed_deadline. Does not wait for extra data."""
    start = t_star(open_time)
    end = deadline(open_time)
    emit = parse_utc(emit_at)
    if emit < start or emit > end:
        return None
    return emit


def time_left_seconds(open_time: datetime | str, close_time: datetime | str) -> float:
    return (parse_utc(close_time) - t_star(open_time)).total_seconds()
