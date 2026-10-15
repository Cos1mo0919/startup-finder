"""Owner decisions for catalog records. Never discard source provenance."""

from sqlalchemy import select

from .catalog_store import history
from .db import Candidate, Project, now_utc


def catalog_action(session, project_id: str, action: str, reason: str = "", target_id: str = "",
                   settings=None) -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError("project_not_found")
    when = now_utc()
    affected_urls = {source.url for source in project.sources}
    if action == "PUBLISH":
        if not project.name or not project.short_description or not project.sources:
            raise ValueError("publication_fields_missing")
        published_before = any(item.get("value") in {"PUBLISHED", "AUTO_PUBLISHED"}
                               for item in project.status_history or [])
        if project.publication_status != "PUBLISHED" and not published_before and settings is not None:
            from .daily import reserve_publication
            from .geography import project_scope
            reserve_publication(session, settings, project_scope(project), when)
        project.publication_status = "PUBLISHED"
        project.visible = True
        project.publication_reason = reason or "admin_verified"
    elif action in ("HIDE", "REJECT"):
        if not reason.strip():
            raise ValueError("reason_required")
        project.publication_status = "REVIEW_REQUIRED" if action == "HIDE" else "REJECTED"
        project.visible = False
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
        project.visible = False
        project.publication_reason = reason or f"merged_into:{target.id}"
    else:
        raise ValueError("invalid_action")
    project.publication_method = "admin"
    project.status_history = history(project.status_history, project.publication_status, "admin", project.publication_reason, when)
    for candidate in session.scalars(select(Candidate)):
        if project.id not in (candidate.project_ids or []) and candidate.url not in affected_urls:
            continue
        linked = [session.get(Project, pid) for pid in candidate.project_ids or []]
        canonical = [p for p in linked if p and p.publication_status == "PUBLISHED"]
        if action == "PUBLISH" and candidate.url in affected_urls:
            candidate.project_ids = list(dict.fromkeys([*(candidate.project_ids or []), project.id]))
            if candidate.entity_type != "PROJECT":
                candidate.classification_history = history(candidate.classification_history,
                    candidate.entity_type, "legacy", "superseded_entity_type", when)
            candidate.entity_type = "PROJECT"
            candidate.status, candidate.reason = "published", ""
        elif candidate.status == "published" and not canonical:
            candidate.status, candidate.reason = "review_required", project.publication_reason
            candidate.status_history = history(candidate.status_history, "REVIEW_REQUIRED", "admin",
                                               candidate.reason, when)
    return {"id": project.id, "status": project.publication_status, "reason": project.publication_reason,
            "target_id": target_id or None}
