"""Preview/guarded recovery of a wholly keyless trial; never run automatically."""

from hashlib import sha256
import json
from sqlalchemy import func, or_, select
from .candidate_budget import candidate_key, candidate_state
from .catalog_store import history
from .dates import TASHKENT
from .db import Candidate, RawDiscovery, Run, SchedulerCheckpoint, aware, now_utc
from .diagnostics import candidate_id
from .raw_discovery import record_transition
from .writer import writer_scope


class RecoveryError(ValueError):
    """Stable non-sensitive reason, never SQL or source content."""


def recover_no_llm(factory, parent_id, first, last, *, apply=False, expected=None):
    if first > last or last - first > 100:
        raise RecoveryError("invalid_child_range")
    today = now_utc().astimezone(TASHKENT).date().isoformat()

    def plan(session):
        parent = session.get(Run, parent_id, with_for_update=apply)
        if (
            not parent
            or parent.status != "completed"
            or parent.details.get("mode") != "free_daily"
            or not parent.details.get("trial")
        ):
            raise RecoveryError("not_completed_trial")
        day = parent.details.get("day", aware(parent.started_at).astimezone(TASHKENT).date().isoformat())
        items = parent.details.get("candidate_runs", [])
        if parent.counts.get("llm_requests", 0) or any(
            value
            for key, value in parent.details.get("usage", {}).items()
            if key.startswith(("llm:", "tokens:"))
        ):
            raise RecoveryError("run_has_llm_usage")
        if any(
            item.get("stage") not in {"review_required", "budget_stopped"}
            or any(
                attempt.get("request_sent") or attempt.get("outcome") != "missing_key"
                for attempt in item.get("provider_attempts", [])
            )
            for item in items
        ):
            raise RecoveryError("run_has_other_outcomes")
        selected = [item for item in items if first <= (item.get("run_id") or -1) <= last]
        if {item["run_id"] for item in selected} != set(range(first, last + 1)):
            raise RecoveryError("child_range_not_owned_by_parent")
        if apply:
            session.get(SchedulerCheckpoint, candidate_key(day, "trial"), with_for_update=True)
        state = candidate_state(session, day, "trial")
        recovery_id = f"missing_key:{parent_id}:{first}:{last}"
        applied = any(item.get("id") == recovery_id for item in state.get("recoveries", []))
        if applied:
            return (
                {"applied": True, "already_applied": True, "requeued": 0, "refunded": 0},
                [],
                [],
                state,
                day,
                recovery_id,
            )
        reserved = parent.details.get("usage", {}).get("candidates", 0)
        if len(items) != 20 or any(
            item.get("stage") != "budget_stopped" for item in items if item not in selected
        ):
            raise RecoveryError("unselected_candidate_outcomes")
        if any(item.get("stage") != "review_required" for item in selected):
            raise RecoveryError("selected_candidate_not_review")
        if (
            reserved != 20
            or parent.counts.get("attempted") != 20
            or state.get("charges", {}).get(str(parent_id)) != reserved
        ):
            raise RecoveryError("expected_20_unrecovered_reservations")
        candidates, raws, children = [], [], []
        for item in selected:
            attempts = item.get("provider_attempts", [])
            if not attempts or {attempt.get("provider") for attempt in attempts} != {"gemini", "groq"}:
                raise RecoveryError("missing_key_evidence_incomplete")
            child = session.get(Run, item["run_id"], with_for_update=apply)
            if child is None or child.status != "completed" or child.counts.get("review_required") != 1:
                raise RecoveryError("child_run_missing_or_not_review")
            children.append(child)
            query = select(Candidate).where(Candidate.last_run_id == child.id)
            rows = list(session.scalars(query.with_for_update() if apply else query))
            if len(rows) != 1:
                raise RecoveryError("candidate_link_ambiguous")
            row = rows[0]
            if (
                candidate_id(row.url) != item["candidate_id"]
                or row.status != "review_required"
                or row.reason != "llm_unavailable"
                or row.project_ids
                or row.review_decision
            ):
                raise RecoveryError("candidate_changed_or_manually_reviewed")
            candidates.append(row)
            raw_query = (
                select(RawDiscovery)
                .where(or_(RawDiscovery.candidate_url == row.url, RawDiscovery.source_url == row.url))
                .order_by(RawDiscovery.id)
            )
            linked = list(session.scalars(raw_query.with_for_update() if apply else raw_query))
            if any(
                raw.status != "review_required"
                or raw.failure_reason != "llm_unavailable"
                or raw.canonical_project_id
                for raw in linked
            ):
                raise RecoveryError("raw_discovery_changed")
            raws.extend(linked)

        # Include every persistent value: even an unrelated evidence/admin edit invalidates preview.
        def values(row):
            return {column.name: getattr(row, column.name) for column in row.__table__.columns}

        snapshot = {
            "today": today,
            "parent": values(parent),
            "children": [values(row) for row in children],
            "candidates": [values(row) for row in candidates],
            "raw": [values(row) for row in raws],
            "state": state,
            "range": [first, last],
        }
        digest = sha256(
            json.dumps(snapshot, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        result = {
            "applied": False,
            "already_applied": False,
            "parent_run": parent_id,
            "child_range": [first, last],
            "budget_day": day,
            "today": today,
            "refund_today": reserved if today == day else 0,
            "requeue_count": len(candidates),
            "refund_candidates": reserved,
            "candidates_before": state["usage"]["candidates"],
            "candidates_after": state["usage"]["candidates"] - reserved,
            "candidate_ids": [candidate_id(row.url) for row in candidates],
            "expected_state": digest,
            "preserved": [
                "run history",
                "evidence",
                "pages",
                "LLM/tokens",
                "daily candidate budget",
                "publications",
            ],
        }
        return result, candidates, raws, state, day, recovery_id

    if not apply:
        with factory() as session:
            return plan(session)[0]
    if not expected:
        raise RecoveryError("preview_hash_required")
    with writer_scope(factory):
        with factory.begin() as session:
            result, candidates, raws, state, day, recovery_id = plan(session)
            if result.get("already_applied"):
                return result
            if result["expected_state"] != expected:
                raise RecoveryError("state_or_day_changed")
            now = now_utc()
            for row in candidates:
                row.status_history = history(
                    row.status_history, row.status.upper(), "repair", "before_missing_key_requeue", now
                )
                row.status, row.reason, row.updated_at = "queued", "", now
                row.status_history = history(row.status_history, "QUEUED", "repair", recovery_id, now)
            for raw in {row.id: row for row in raws}.values():
                record_transition(raw, "pending", recovery_id, when=now)
            key = candidate_key(day, "trial")
            checkpoint = session.get(SchedulerCheckpoint, key)
            if checkpoint is None:
                checkpoint = SchedulerCheckpoint(name=key, cursor={})
                session.add(checkpoint)
            charges = {**state["charges"], str(parent_id): 0}
            checkpoint.cursor = {
                **state,
                "charges": charges,
                "usage": {"candidates": sum(charges.values())},
                "candidate_limits": state.get("candidate_limits", (20, 20)),
                "recoveries": [
                    *state.get("recoveries", []),
                    {
                        "id": recovery_id,
                        "at": now.isoformat(),
                        "refunded": result["refund_candidates"],
                        "requeued": len(candidates),
                        "expected_state": expected,
                    },
                ],
            }
            session.flush()
            verified = session.scalar(
                select(func.count())
                .select_from(Candidate)
                .where(
                    Candidate.url.in_([row.url for row in candidates]),
                    Candidate.status == "queued",
                    Candidate.reason == "",
                )
            )
            if (
                verified != result["requeue_count"]
                or checkpoint.cursor["usage"]["candidates"] != result["candidates_after"]
            ):
                raise RecoveryError("recovery_count_mismatch")
            return {**result, "applied": True}
