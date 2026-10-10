"""Durable source observations and cheap, conservative pre-classification checks."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select

from .db import Project, RawDiscovery, Source, now_utc
from .network import canonical_url

NOISE_TITLE = re.compile(
    r"\b(stipendiya|scholarship|стипендия|вакансия|vakansiya|job opening|"
    r"reklama|advertisement|political appointment)\b", re.I,
)
PROJECT_HINT = re.compile(r"\b(startup|startap|project|loyiha|platform|app|prototype|prototip|product|ilova)\b", re.I)


def ingest_raw(session, *, source_adapter: str, source_url: str, source_name: str = "",
               source_type: str = "", page_type: str = "", external_id: str | None = None,
               title: str = "", description: str = "", raw_text: str | None = None,
               raw_payload: dict | None = None, publication_date: datetime | None = None,
               discovered_at: datetime | None = None) -> tuple[RawDiscovery, bool]:
    """Create one observation per adapter and URL, idempotent across polling."""
    url = canonical_url(source_url)
    if external_id:
        existing = session.scalar(select(RawDiscovery).where(
            RawDiscovery.source_adapter == source_adapter, RawDiscovery.external_id == external_id))
        if existing:
            return existing, False
    existing = session.scalar(select(RawDiscovery).where(
        RawDiscovery.source_adapter == source_adapter, RawDiscovery.source_url == url))
    if existing:
        return existing, False
    row = RawDiscovery(source_adapter=source_adapter, source_url=url, source_name=source_name,
                       source_type=source_type, page_type=page_type, external_id=external_id,
                       title=title, description=description, raw_text=raw_text,
                       raw_payload=raw_payload or {}, publication_date=publication_date,
                       discovered_at=discovered_at or now_utc(), status="pending")
    session.add(row)
    session.flush()
    return row, True


def cheap_decision(session, row: RawDiscovery) -> tuple[str, str, str | None]:
    """Return (action, reason, project_id); uncertain content continues."""
    project = session.scalar(select(Project).join(Source, Source.project_id == Project.id)
                             .where(Source.url == row.source_url))
    if project:
        return "duplicate", "known_project_source", project.id
    if NOISE_TITLE.search(row.title or "") and not PROJECT_HINT.search(row.title or ""):
        return "reject", "obvious_noise", None
    return "classify", "", None


def record_transition(row: RawDiscovery, status: str, reason: str = "", project_id: str | None = None,
                      when: datetime | None = None) -> None:
    when = when or now_utc()
    row.status = status
    row.failure_reason = reason or None
    row.canonical_project_id = project_id or row.canonical_project_id
    row.processed_at = when if status in {"processed", "review_required", "rejected", "failed"} else None
    row.processing_history = [*(row.processing_history or []),
                              {"at": when.isoformat(), "status": status, "reason": reason,
                               "project_id": row.canonical_project_id}]
