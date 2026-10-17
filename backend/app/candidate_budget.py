"""Mode-specific candidate reservations, including conservative legacy reconstruction."""

from datetime import datetime, timedelta
from sqlalchemy import select
from .dates import TASHKENT
from .db import Run, SchedulerCheckpoint, aware


def candidate_key(day, mode):
    if mode not in {"trial", "daily"}:
        raise ValueError("Invalid candidate budget mode")
    return f"free_candidates:{mode}:{day}"


def candidate_state(session, day, mode):
    row = session.get(SchedulerCheckpoint, candidate_key(day, mode))
    if row:
        return row.cursor
    start = datetime.fromisoformat(day).replace(tzinfo=TASHKENT)
    charges = {}
    for run in session.scalars(
        select(Run).where(
            Run.started_at >= start - timedelta(hours=1),
            Run.started_at < start + timedelta(days=1),
            Run.details["mode"].as_string() == "free_daily",
        )
    ):
        data = run.details or {}
        if bool(data.get("trial")) != (mode == "trial"):
            continue
        events = [
            event
            for event in data.get("budget_events", [])
            if event.get("resource") == "candidates"
            and aware(datetime.fromisoformat(event["at"])).astimezone(TASHKENT).date().isoformat() == day
        ]
        amount = (
            len(events)
            if events
            else data.get("usage", {}).get("candidates", 0)
            if data.get("day", aware(run.started_at).astimezone(TASHKENT).date().isoformat()) == day
            else 0
        )
        if amount:
            charges[str(run.id)] = amount
    return {
        "usage": {"candidates": sum(charges.values())},
        "charges": charges,
        "attempts": dict(charges),
        "recoveries": [],
    }


class CandidateBudget:
    def __init__(self, budget, mode):
        self.key = candidate_key(budget.day, mode)
        self.mode = mode
        with budget.factory.begin() as session:
            row = session.get(SchedulerCheckpoint, self.key)
            if row is None:
                row = SchedulerCheckpoint(name=self.key, cursor=candidate_state(session, budget.day, mode))
                session.add(row)
            row.cursor = {**row.cursor, "candidate_limits": budget.limits.get("candidates", (0, 0))}
