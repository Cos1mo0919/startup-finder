"""When a project appeared on the public site, and the home / recent windows.

"New" on the home page and in "So‘nggi paytda" means *added to izlanish* on that
Tashkent day or week, not the date of the source article (which stays on the card
and drives the archive).
"""
from datetime import datetime, timedelta, timezone

from .db import aware
from .dates import TASHKENT, today_start

PUBLISHED_VALUES = {"AUTO_PUBLISHED", "PUBLISHED"}


def site_added_at(project) -> datetime:
    """First transition to a published state; first_seen for legacy rows."""
    stamps = []
    for item in project.status_history or []:
        if isinstance(item, dict) and item.get("value") in PUBLISHED_VALUES and item.get("timestamp"):
            try:
                stamps.append(aware(datetime.fromisoformat(item["timestamp"])))
            except (TypeError, ValueError):
                continue
    return min(stamps) if stamps else aware(project.first_seen)


def _newest_first(pairs):
    return [project for _, project in sorted(pairs, key=lambda pair: (pair[0], pair[1].id), reverse=True)]


def home_window(projects, now):
    """Projects added today; before today's run, yesterday's; else the latest day with additions."""
    today = today_start(now)
    tomorrow = today + timedelta(days=1)
    added = [(site_added_at(project), project) for project in projects]
    for label, start, end in (("today", today, tomorrow), ("yesterday", today - timedelta(days=1), today)):
        window = [pair for pair in added if start <= pair[0] < end]
        if window:
            return label, start, _newest_first(window)
    earlier = [pair for pair in added if pair[0] < today - timedelta(days=1)]
    if not earlier:
        return "empty", None, []
    latest_day = max(stamp for stamp, _ in earlier).astimezone(TASHKENT).date()
    start = datetime(latest_day.year, latest_day.month, latest_day.day, tzinfo=TASHKENT).astimezone(timezone.utc)
    window = [pair for pair in earlier if start <= pair[0] < start + timedelta(days=1)]
    return "latest", start, _newest_first(window)


def recent_week(now):
    """Monday–Wednesday: the previous Monday–Sunday week; Thursday–Sunday: the current week."""
    local = aware(now).astimezone(TASHKENT)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if local.weekday() <= 2:
        return "last_week", monday - timedelta(days=7), monday
    return "this_week", monday, monday + timedelta(days=7)


def recent_window(projects, now):
    label, start, end = recent_week(now)
    start_utc, end_utc = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    window = [(stamp, project) for project in projects
              if start_utc <= (stamp := site_added_at(project)) < end_utc]
    return label, start, end, _newest_first(window)
