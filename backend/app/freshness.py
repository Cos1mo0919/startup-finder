"""Home-page day window and the catalog "So‘nggi paytda" week, by the card date.

The card date is ``published_at``: the source article date, or the discovery
date when the article date is unknown ("taxminiy"). Old articles found today
therefore stay out of "today" and "recent" views.
"""
from datetime import datetime, timedelta, timezone

from .db import aware
from .dates import TASHKENT, today_start


def _newest_first(pairs):
    return [project for _, project in sorted(pairs, key=lambda pair: (pair[0], pair[1].id), reverse=True)]


def home_window(projects, now):
    """Projects dated today; else yesterday (e.g. before the 20:00 run); else the latest
    day within the past week. Older projects never appear on the home page."""
    today = today_start(now)
    tomorrow = today + timedelta(days=1)
    dated = [(aware(project.published_at), project) for project in projects]
    for label, start, end in (("today", today, tomorrow), ("yesterday", today - timedelta(days=1), today)):
        window = [pair for pair in dated if start <= pair[0] < end]
        if window:
            return label, start, _newest_first(window)
    earlier = [pair for pair in dated if today - timedelta(days=7) <= pair[0] < today - timedelta(days=1)]
    if not earlier:
        return "empty", None, []
    latest_day = max(stamp for stamp, _ in earlier).astimezone(TASHKENT).date()
    start = datetime(latest_day.year, latest_day.month, latest_day.day, tzinfo=TASHKENT).astimezone(timezone.utc)
    window = [pair for pair in earlier if start <= pair[0] < start + timedelta(days=1)]
    return "latest", start, _newest_first(window)


def recent_week(now):
    """Monday–Wednesday: the previous Monday–Sunday week; Thursday–Sunday: the current week.

    Returns (label, start, end) with Tashkent-aware bounds; ``end`` is exclusive."""
    local = aware(now).astimezone(TASHKENT)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if local.weekday() <= 2:
        return "last_week", monday - timedelta(days=7), monday
    return "this_week", monday, monday + timedelta(days=7)


def recent_summary(now):
    label, start, end = recent_week(now)
    return {"period": label, "start": start.date().isoformat(), "end": (end - timedelta(days=1)).date().isoformat()}
