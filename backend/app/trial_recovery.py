"""Preview/apply recovery for a trial that consumed candidates while no LLM was usable."""

from datetime import datetime
import hashlib
import json

from sqlalchemy import select

from .dates import TASHKENT
from .db import Candidate, Run, SchedulerCheckpoint, aware, now_utc
from .free_daily import candidate_budget_key
from .writer import writer_scope


def _child_ids(start_run, end_run):
    if start_run > end_run:
        raise ValueError("child run range is reversed")
    return list(range(start_run, end_run + 1))


def _snapshot(session, *, parent_run, start_run, end_run, refund_candidates):
    parent = session.get(Run, parent_run)
    if parent is None:
        raise ValueError("parent run not found")
    details = parent.details or {}
    if details.get("mode") != "free_daily" or not details.get("trial"):
        raise ValueError("parent run is not a trial free_daily run")
    day = details.get("day") or aware(parent.started_at).astimezone(TASHKENT).date().isoformat()
    ids = _child_ids(start_run, end_run)
    children = list(session.scalars(select(Run).where(Run.id.in_(ids)).order_by(Run.id)))
    found_ids = [row.id for row in children]
    if found_ids != ids:
        missing = sorted(set(ids) - set(found_ids))
        raise ValueError(f"child runs missing: {missing}")
    candidates = list(session.scalars(select(Candidate).where(Candidate.last_run_id.in_(ids)).order_by(Candidate.last_run_id, Candidate.url)))
    eligible = [row for row in candidates if row.reason == "llm_unavailable" and row.status in {"review_required", "pending", "error"}]
    rejected = [{"run_id": row.last_run_id, "url": row.url, "status": row.status, "reason": row.reason}
                for row in candidates if row not in eligible]
    counter = session.get(SchedulerCheckpoint, candidate_budget_key(day, "trial"))
    state = counter.cursor if counter else {"usage": {}}
    charged = state.get("usage", {}).get("candidates", 0)
    if refund_candidates < 0 or refund_candidates > charged:
        raise ValueError("candidate refund exceeds today's charged trial candidates")
    return {
        "day": day,
        "parent_run": parent_run,
        "child_runs": ids,
        "eligible": [{"run_id": row.last_run_id, "url": row.url} for row in eligible],
        "ineligible": rejected,
        "refund_candidates": refund_candidates,
        "charged_before": charged,
        "charged_after": charged - refund_candidates,
        "counter_state": state,
    }


def _digest(snapshot):
    stable = {key: snapshot[key] for key in (
        "day", "parent_run", "child_runs", "eligible", "ineligible",
        "refund_candidates", "charged_before", "counter_state")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def recover_trial_llm_unavailable(factory, *, parent_run, start_run, end_run, refund_candidates,
                                  apply=False, expected=None):
    """Requeue only llm_unavailable candidates and refund an explicit trial candidate charge.

    Preview is read-only. Apply runs under the global writer lease, verifies the preview
    fingerprint, appends recovery history to the parent run, and leaves child run rows intact.
    """
    def preview(session):
        snap = _snapshot(session, parent_run=parent_run, start_run=start_run, end_run=end_run,
                         refund_candidates=refund_candidates)
        return {
            "applied": False,
            "expected_state": _digest(snap),
            "day": snap["day"],
            "parent_run": parent_run,
            "child_run_range": [start_run, end_run],
            "eligible_candidates": len(snap["eligible"]),
            "eligible": snap["eligible"],
            "ineligible": snap["ineligible"],
            "trial_candidates_before": snap["charged_before"],
            "trial_candidates_after": snap["charged_after"],
            "refund_candidates": refund_candidates,
            "preserved": ["run rows", "candidate attempts/history", "daily candidate budget", "page budget", "LLM/token ledgers"],
        }

    if not apply:
        with factory() as session:
            return preview(session)
    if not expected:
        raise ValueError("Run the read-only preview first and supply --expect-state")
    with writer_scope(factory):
        with factory.begin() as session:
            snap = _snapshot(session, parent_run=parent_run, start_run=start_run, end_run=end_run,
                             refund_candidates=refund_candidates)
            current = _digest(snap)
            if current != expected:
                raise ValueError("Recovery state changed; repeat the read-only preview")
            when = now_utc()
            ids = snap["child_runs"]
            rows = list(session.scalars(select(Candidate).where(Candidate.last_run_id.in_(ids))))
            eligible_urls = {item["url"] for item in snap["eligible"]}
            for row in rows:
                if row.url not in eligible_urls:
                    continue
                row.status = "queued"
                row.reason = ""
                row.analysis_mode = ""
                row.updated_at = when
                row.status_history = [*(row.status_history or []), {
                    "at": when.isoformat(), "from": "review_required", "to": "queued",
                    "reason": "operator_requeue_llm_unavailable", "parent_run": parent_run,
                }]
            key = candidate_budget_key(snap["day"], "trial")
            counter = session.get(SchedulerCheckpoint, key)
            if counter is None:
                raise ValueError("trial candidate budget state missing")
            usage = dict(counter.cursor.get("usage", {}))
            usage["candidates"] = snap["charged_after"]
            counter.cursor = {**counter.cursor, "usage": usage,
                              "recoveries": [*counter.cursor.get("recoveries", []), {
                                  "at": when.isoformat(), "parent_run": parent_run,
                                  "child_run_range": [start_run, end_run],
                                  "requeued": len(eligible_urls), "refunded": refund_candidates,
                                  "expected_state": expected,
                              }]}
            parent = session.get(Run, parent_run)
            parent.details = {**(parent.details or {}), "operator_recoveries": [
                *((parent.details or {}).get("operator_recoveries", [])),
                {"at": when.isoformat(), "child_run_range": [start_run, end_run],
                 "requeued": len(eligible_urls), "refunded_candidates": refund_candidates,
                 "expected_state": expected},
            ]}
            result = preview(session)
            return {**result, "applied": True}
