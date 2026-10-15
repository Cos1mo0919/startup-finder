"""Separate trial/daily page allowances. Keep physical attempts when refunding failures."""

from datetime import datetime, timedelta
import hashlib
import json

from sqlalchemy import select

from .dates import TASHKENT
from .db import Run, SchedulerCheckpoint, aware, now_utc


def page_key(day, mode):
    if mode not in {"trial", "daily"}:
        raise ValueError("Invalid page budget mode")
    return f"free_pages:{mode}:{day}"


def initial_state(session, day, mode):
    start = datetime.fromisoformat(day).replace(tzinfo=TASHKENT)
    rows = session.scalars(
        select(Run).where(
            Run.started_at >= start - timedelta(hours=1),
            Run.started_at < start + timedelta(days=1),
            Run.details["mode"].as_string() == "free_daily",
        )
    )
    charges, attempts, refunds, events = {}, {}, {}, []
    for run in rows:
        data = run.details or {}
        if bool(data.get("trial")) != (mode == "trial"):
            continue
        items = [
            event
            for event in data.get("budget_events", [])
            if event.get("resource") == "pages"
            and aware(datetime.fromisoformat(event["at"])).astimezone(TASHKENT).date().isoformat() == day
        ]
        amount = (
            len(items)
            if items
            else (
                data.get("usage", {}).get("pages", 0)
                if data.get("day", aware(run.started_at).astimezone(TASHKENT).date().isoformat()) == day
                else 0
            )
        )
        if not amount:
            continue
        key = str(run.id)
        attempts[key] = amount
        failed = run.status in {"failed", "interrupted"}
        charges[key] = 0 if failed else amount
        if failed:
            refunds[key] = amount
        events.extend({**item, "run_id": run.id} for item in items)
    return {
        "usage": {"pages": sum(charges.values())},
        "charges": charges,
        "attempts": attempts,
        "refunds": refunds,
        "events": events,
        "resets": [],
    }


def load_state(session, day, mode):
    row = session.get(SchedulerCheckpoint, page_key(day, mode))
    return row.cursor if row else initial_state(session, day, mode)


def refund_run(session, row, run_id):
    key = str(run_id)
    amount = row.cursor.get("charges", {}).get(key, 0)
    if not amount:
        return 0
    charges = {**row.cursor.get("charges", {}), key: 0}
    row.cursor = {
        **row.cursor,
        "charges": charges,
        "usage": {"pages": sum(charges.values())},
        "refunds": {**row.cursor.get("refunds", {}), key: amount},
    }
    return amount


class PageBudget:
    def __init__(self, budget, mode):
        self.budget, self.mode = budget, mode
        self.key = page_key(budget.day, mode)
        with budget.factory.begin() as session:
            run = session.get(Run, budget.run_id)
            if run:
                run.details = {**run.details, "trial": mode == "trial", "day": budget.day}
            row = session.get(SchedulerCheckpoint, self.key)
            if row is None:
                row = SchedulerCheckpoint(name=self.key, cursor=initial_state(session, budget.day, mode))
                session.add(row)
            # A previous process may have died before its final refund. The shared
            # writer has already marked abandoned runs interrupted.
            for identifier, amount in list(row.cursor.get("charges", {}).items()):
                run = session.get(Run, int(identifier)) if amount else None
                if run and run.status in {"failed", "interrupted"}:
                    refund_run(session, row, run.id)
            row.cursor = {**row.cursor, "page_limits": budget.limits["pages"]}

    def refund(self, session):
        row = session.get(SchedulerCheckpoint, self.key)
        return refund_run(session, row, self.budget.run_id)


def state_digest(day, state):
    return hashlib.sha256(
        json.dumps(
            {"day": day, "mode": "trial", "state": state}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def reset_trial_pages(factory, *, apply=False, expected=None, limits=(40, 40)):
    from .writer import writer_scope

    day = now_utc().astimezone(TASHKENT).date().isoformat()

    def preview(session):
        state = load_state(session, day, "trial")
        return state, {
            "day": day,
            "timezone": "Asia/Tashkent",
            "mode": "trial",
            "pages_before": state["usage"]["pages"],
            "pages_after": 0,
            "expected_state": state_digest(day, state),
            "applied": False,
            "preserved": ["daily page budget", "LLM requests/tokens", "publication counts", "run history"],
        }

    if not apply:
        with factory() as session:
            return preview(session)[1]
    if not expected:
        raise ValueError("Run the read-only preview first and supply --expect-state")
    with writer_scope(factory):
        with factory.begin() as session:
            state, result = preview(session)
            if expected != result["expected_state"]:
                raise ValueError("Budget changed or Tashkent day changed; repeat the preview")
            row = session.get(SchedulerCheckpoint, page_key(day, "trial"))
            if row is None:
                row = SchedulerCheckpoint(name=page_key(day, "trial"), cursor={})
                session.add(row)
            row.cursor = {
                **state,
                "page_limits": limits,
                "usage": {"pages": 0},
                "charges": {key: 0 for key in state.get("charges", {})},
                "resets": [
                    *state.get("resets", []),
                    {
                        "at": now_utc().isoformat(),
                        "pages": result["pages_before"],
                        "actor": "operator_cli",
                        "expected_state": expected,
                    },
                ],
            }
            return {**result, "applied": True}
