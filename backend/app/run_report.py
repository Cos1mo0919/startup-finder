"""Candidate-level outcomes; a returned pipeline call is not a classification."""

from sqlalchemy import select
from .db import Candidate, Run
from .diagnostics import candidate_id


def candidate_outcome(factory, url, result):
    with factory() as session:
        from .db import RegistrySource
        pair = session.execute(select(Candidate, RegistrySource).outerjoin(RegistrySource, RegistrySource.id == Candidate.source_id).where(Candidate.url == url)).first()
        row, source = pair if pair else (None, None)
        status = row.status if row else "missing"
        reason = row.reason if row else "candidate_missing"
        from urllib.parse import urlsplit
        source_info = {"id": row.source_id if row else None, "name": source.name if source else urlsplit(url).hostname,
                       "domain": urlsplit(url).hostname,
                       "page_type": ((row.article or {}).get("page_type") if row else None) or ((source.options or {}).get("page_type") if source else None) or "unknown"}
    stopped = result.get("status") == "stopped"
    stage = (
        "budget_stopped"
        if stopped
        else "no_decision"
        if not result.get("counts", {}).get("candidates", 0)
        else "timeout"
        if reason == "candidate_timeout"
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
        "source": source_info,
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
        if recorded:
            enriched = []
            for item in recorded:
                child = session.get(Run, item.get("run_id")) if item.get("run_id") else None
                update = dict(item)
                if child:
                    candidate = session.scalar(select(Candidate).where(Candidate.last_run_id == child.id).limit(1))
                    if candidate is None:
                        urls = [error.get("source") for error in child.errors if error.get("stage") == "fetch"]
                        candidate = session.get(Candidate, urls[0]) if urls else None
                    if candidate:
                        update.setdefault("source", candidate_outcome(factory, candidate.url, {"counts": child.counts})["source"])
                    update["provider_metrics"] = child.details.get("llm_providers", [])
                    if "timings_ms" not in update:
                        update["timings_available"] = False
                enriched.append(update)
            recorded = enriched
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
                        "diagnostics": child.details.get("diagnostics"),
                        "llm_providers": child.details.get("llm_providers", []),
                    }
                )
        return {
            "id": row.id,
            "status": row.status,
            "counts": row.counts,
            "stop_reason": row.details.get("stop_reason"),
            "errors": row.errors,
            "candidate_runs": recorded,
            "diagnostics_available": any("timings_ms" in item for item in (recorded or [])),
            "legacy_children_inferred": recorded is None,
            "inferred_children": children,
        }
