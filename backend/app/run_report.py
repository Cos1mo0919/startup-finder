"""Candidate-level outcomes; a returned pipeline call is not a classification."""

from sqlalchemy import select
from .db import Candidate, Run
from .diagnostics import candidate_id


def candidate_outcome(factory, url, result):
    with factory() as session:
        row = session.get(Candidate, url)
        status = row.status if row else "missing"
        reason = row.reason if row else "candidate_missing"
    stopped = result.get("status") == "stopped"
    stage = (
        "budget_stopped"
        if stopped
        else "no_decision"
        if not result.get("counts", {}).get("candidates", 0)
        else "fetch_failed"
        if status == "error"
        else "duplicate"
        if status == "published" and result.get("counts", {}).get("duplicates")
        else status
        if status in {"published", "rejected", "review_required", "pending"}
        else "no_decision"
    )
    return {
        "candidate_id": candidate_id(url),
        "run_id": result.get("id"),
        "status": status,
        "stage": stage,
        "reason": reason[:200],
        "stop_reason": result.get("details", {}).get("stop_reason", ""),
        "error_codes": [item.get("code", "")[:120] for item in result.get("errors", [])],
    }


def inspect_run(factory, identifier):
    with factory() as session:
        row = session.get(Run, identifier)
        if row is None:
            raise ValueError("Run not found")
        recorded = row.details.get("candidate_runs")
        children = []
        if recorded is None:
            # Old runs lack parent IDs: report this inference explicitly.
            query = select(Run).where(
                Run.id > row.id,
                Run.started_at >= row.started_at,
                Run.details["mode"].as_string().in_(["catalog_fresh", "catalog_archive"]),
            )
            if row.finished_at:
                query = query.where(Run.started_at <= row.finished_at)
            for child in session.scalars(query.order_by(Run.id).limit(200)):
                children.append(
                    {
                        "id": child.id,
                        "status": child.status,
                        "counts": child.counts,
                        "errors": child.errors,
                        "stop_reason": child.details.get("stop_reason"),
                    }
                )
        return {
            "id": row.id,
            "status": row.status,
            "counts": row.counts,
            "stop_reason": row.details.get("stop_reason"),
            "errors": row.errors,
            "candidate_runs": recorded,
            "legacy_children_inferred": recorded is None,
            "inferred_children": children,
        }
