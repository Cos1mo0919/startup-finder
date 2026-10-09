"""Owner decisions for catalog records. Never discard source provenance."""

from sqlalchemy import select

from .catalog_store import history
from .db import Candidate, Project, now_utc


def catalog_action(session, project_id: str, action: str, reason: str = "", target_id: str = "") -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError("project_not_found")
    when = now_utc()
    if action == "PUBLISH":
        if not project.name or not project.short_description or not project.sources:
            raise ValueError("publication_fields_missing")
        project.publication_status = "PUBLISHED"
        project.publication_reason = reason or "admin_verified"
    elif action in ("HIDE", "REJECT"):
        if not reason.strip():
            raise ValueError("reason_required")
        project.publication_status = "REVIEW_REQUIRED" if action == "HIDE" else "REJECTED"
        project.publication_reason = reason
        project.review_reason = reason
    elif action == "MERGE":
        target = session.get(Project, target_id)
        if target is None or target.id == project.id:
            raise ValueError("merge_target_invalid")
        existing_urls = {source.url for source in target.sources}
        for source in list(project.sources):
            if source.url not in existing_urls:
                source.project_id = target.id
                target.sources.append(source)
                existing_urls.add(source.url)
        for evidence in list(project.evidence_records):
            evidence.project_id = target.id
            target.evidence_records.append(evidence)
        target.aliases = list(dict.fromkeys([*(target.aliases or []), project.name, *(project.aliases or [])]))
        target.first_seen = min(target.first_seen, project.first_seen)
        target.last_seen = max(target.last_seen, project.last_seen)
        target.status_history = history(target.status_history, "MERGE_RECEIVED", "admin", reason or project.id, when)
        for candidate in session.scalars(select(Candidate)):
            if project.id in (candidate.project_ids or []):
                candidate.project_ids = list(dict.fromkeys(target.id if pid == project.id else pid for pid in candidate.project_ids))
        project.publication_status = "DUPLICATE"
        project.publication_reason = reason or f"merged_into:{target.id}"
    else:
        raise ValueError("invalid_action")
    project.publication_method = "admin"
    project.status_history = history(project.status_history, project.publication_status, "admin", project.publication_reason, when)
    return {"id": project.id, "status": project.publication_status, "reason": project.publication_reason,
            "target_id": target_id or None}
