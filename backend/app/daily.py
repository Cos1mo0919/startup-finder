"""Durable daily publication budget, counted at publication rather than source date."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select, update

from .db import Candidate, DailyStats, RegistrySource, aware, now_utc


class DailyLimitReached(ValueError):
    def __init__(self, reason="daily_publish_limit_reached"):
        self.reason = reason
        super().__init__(reason)


def calendar_day(when: datetime, settings) -> str:
    return aware(when).astimezone(ZoneInfo(settings.scheduler_timezone)).date().isoformat()


def _ensure_row(session, day: str):
    dialect = session.bind.dialect.name
    if dialect == "sqlite":
        session.execute(insert(DailyStats).values(day=day).prefix_with("OR IGNORE"))
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        session.execute(pg_insert(DailyStats).values(day=day).on_conflict_do_nothing(index_elements=["day"]))
    elif session.get(DailyStats, day) is None:
        session.add(DailyStats(day=day))
        session.flush()


def today_stats(session, settings, when=None):
    day = calendar_day(when or now_utc(), settings)
    row = session.get(DailyStats, day)
    return {"day": day, "published": row.published_count if row else 0,
            "uzbekistan": row.uzbekistan_count if row else 0,
            "global": row.global_count if row else 0,
            "github": row.github_count if row else 0, "limit": settings.daily_publish_limit,
            "uzbekistan_target": min(settings.daily_uz_limit, settings.daily_publish_limit)}


def publication_summary(session, settings, when=None):
    now = when or now_utc()
    today = today_stats(session, settings, now)
    day = datetime.fromisoformat(today["day"]).date()
    week = session.scalar(select(func.coalesce(func.sum(DailyStats.published_count), 0)).where(
        DailyStats.day >= (day - timedelta(days=6)).isoformat(), DailyStats.day <= today["day"]))
    month = session.scalar(select(func.coalesce(func.sum(DailyStats.published_count), 0)).where(
        DailyStats.day >= day.replace(day=1).isoformat(), DailyStats.day <= today["day"]))
    return {**today, "week": week or 0, "month": month or 0}


def reserve_publication(session, settings, section: str, when=None, current_url=None):
    """Atomically reserve one slot for a new PUBLISHED transition."""
    day = calendar_day(when or now_utc(), settings)
    _ensure_row(session, day)
    column = {"Uzbekistan": DailyStats.uzbekistan_count,
              "Global": DailyStats.global_count, "GitHub": DailyStats.github_count}[section]
    conditions = [DailyStats.day == day,
                  DailyStats.published_count < settings.daily_publish_limit]
    if section != "Uzbekistan":
        # Preserve up to the local target while actionable local work exists.
        local_query = select(func.count()).select_from(Candidate).join(
            RegistrySource, Candidate.source_id == RegistrySource.id).where(
            Candidate.status == "queued", RegistrySource.country == "Uzbekistan")
        if current_url:
            local_query = local_query.where(Candidate.url != current_url)
        local_queued = session.scalar(local_query) or 0
        if local_queued:
            conditions.append(DailyStats.global_count + DailyStats.github_count <
                              settings.daily_publish_limit - min(settings.daily_uz_limit,
                                                                 settings.daily_publish_limit))
    changed = session.execute(update(DailyStats).where(*conditions).values(
        published_count=DailyStats.published_count + 1,
        **{column.key: column + 1})).rowcount
    if not changed:
        row = session.get(DailyStats, day)
        reason = ("daily_publish_limit_reached" if row.published_count >= settings.daily_publish_limit
                  else "local_reservation_active")
        raise DailyLimitReached(reason)
