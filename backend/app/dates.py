from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dateutil.parser import parse
from .db import aware

TASHKENT = ZoneInfo("Asia/Tashkent")
CUTOFF = datetime(2022, 1, 1, tzinfo=timezone.utc)


def parse_date(raw):
    if not raw:
        return None
    try:
        value = parse(str(raw))
        # Source timestamps without an offset are interpreted in Uzbekistan local time.
        if value.tzinfo is None:
            value = value.replace(tzinfo=TASHKENT)
        return value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def valid_date(value, now, archive=False):
    if value is None:
        return False
    value, now = aware(value), aware(now)
    return CUTOFF <= value <= now and (archive or value >= now - timedelta(days=30))


def priority(value, now):
    if value is None:
        return 6
    age = aware(now) - aware(value)
    if age <= timedelta(hours=1):
        return 0
    if aware(value).astimezone(TASHKENT).date() == aware(now).astimezone(TASHKENT).date():
        return 1
    if aware(value).astimezone(TASHKENT).date() == aware(now).astimezone(TASHKENT).date() - timedelta(days=1):
        return 2
    return 3 if age <= timedelta(days=7) else 4 if age <= timedelta(days=30) else 5


def today_start(now):
    return (
        aware(now)
        .astimezone(TASHKENT)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
    )
