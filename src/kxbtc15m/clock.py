"""15-minute UTC buckets and America/Denver calendar days."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")


def parse_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def bucket_id(close_time: datetime | str) -> str:
    dt = parse_utc(close_time).replace(second=0, microsecond=0)
    minute = (dt.minute // 15) * 15
    dt = dt.replace(minute=minute)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def denver_day(utc_dt: datetime | str) -> date:
    return parse_utc(utc_dt).astimezone(DENVER).date()
