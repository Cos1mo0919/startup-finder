from datetime import timedelta
from sqlalchemy import func, select
from .db import (
    Run,
    Candidate,
    EcosystemSignal,
    Event,
    Project,
    RegistrySource,
    RejectedCandidate,
    aware,
    now_utc,
)
from .dates import today_start
from .diagnostics import candidate_diagnostics
from .evidence import EVIDENCE_LABELS, STOP_LABELS
from .sectors import SECTORS


def iso(value):
    return aware(value).isoformat() if value else None


def source_json(s):
    status = (
        "DISABLED"
        if not s.enabled
        else "NEEDS_CONFIG"
        if s.last_error in ("requires_api_key", "source_requires_configuration")
        else "ERROR"
        if s.consecutive_errors
        else "ACTIVE"
        if s.last_success_at
        else "UNTESTED"
    )
    return {
        k: getattr(s, k)
        for k in (
            "id",
            "name",
            "url",
            "source_type",
            "region",
            "priority",
            "check_frequency",
            "reliability_score",
            "enabled",
            "collection_method",
            "consecutive_errors",
            "candidates_found",
            "new_projects",
            "last_error",
            "notes",
        )
    } | {
        "status": status,
        "last_checked_at": iso(s.last_checked_at),
        "last_success_at": iso(s.last_success_at),
        "next_check_at": iso(aware(s.last_checked_at) + timedelta(minutes=s.check_frequency))
        if s.enabled and s.last_checked_at
        else None,
    }


def radar_status(session, threshold):
    now = now_utc()
    sources = list(
        session.scalars(select(RegistrySource).order_by(RegistrySource.priority.desc(), RegistrySource.name))
    )
    projects = list(session.scalars(select(Project)))
    visible = [p for p in projects if p.visible]
    events = list(session.scalars(select(Event).order_by(Event.discovered_at.desc()).limit(100)))
    rejected = list(
        session.scalars(select(RejectedCandidate).order_by(RejectedCandidate.rejected_at.desc()).limit(30))
    )
    signals = list(
        session.scalars(select(EcosystemSignal).order_by(EcosystemSignal.discovered_at.desc()).limit(30))
    )
    return {
        **candidate_diagnostics(session),
        "sources": [source_json(s) for s in sources],
        "source_summary": {
            "total": len(sources),
            "active": sum(s.enabled for s in sources),
            "failed": sum(
                s.enabled
                and s.consecutive_errors > 0
                and s.last_error not in ("requires_api_key", "source_requires_configuration")
                for s in sources
            ),
            "priority_5": sum(s.priority == 5 for s in sources),
            "last_check": max((iso(s.last_checked_at) for s in sources if s.last_checked_at), default=None),
        },
        "events": [
            {
                "id": e.id,
                "name": e.name,
                "event_type": e.event_type,
                "organizer": e.organizer,
                "city": e.city,
                "country": e.country,
                "start_date": iso(e.start_date),
                "end_date": iso(e.end_date),
                "official_url": e.official_url,
                "source_url": e.source_url,
                "source_id": e.source_id,
                "status": e.status,
                "last_checked_at": iso(e.last_checked_at),
                "last_error": e.last_error,
                "discovered_at": iso(e.discovered_at),
                "projects_found": sum(p.visible and p.event_id == e.id for p in projects),
            }
            for e in events
        ],
        "event_summary": {
            "total": session.scalar(select(func.count()).select_from(Event)),
            "today": session.scalar(
                select(func.count()).select_from(Event).where(Event.discovered_at >= today_start(now))
            ),
            "projects_found": sum(p.event_id is not None for p in visible),
        },
        "candidate_summary": {
            "total": session.scalar(select(func.count()).select_from(Candidate)),
            "accepted": len(visible),
            "duplicates": sum(r.counts.get("duplicates", 0) for r in session.scalars(select(Run))),
            "stop_filtered": session.scalar(select(func.count()).select_from(RejectedCandidate)),
            "ecosystem_signals": session.scalar(select(func.count()).select_from(EcosystemSignal)),
        },
        "evidence_summary": {
            "average": round(sum(p.confidence for p in visible) / len(visible), 2) if visible else 0,
            "low_confidence": sum(p.confidence < threshold for p in projects),
            "single_source": sum(len(p.sources) == 1 for p in visible),
            "multiple_sources": sum(len(p.sources) > 1 for p in visible),
            "hidden_projects": sum(not p.visible for p in projects),
            "threshold": threshold,
        },
        "rejected_candidates": [
            {
                "url": r.url,
                "title": r.title,
                "reasons": r.reasons,
                "reason_labels": [STOP_LABELS.get(x, x) for x in r.reasons],
                "evidence_score": r.evidence_score,
                "signals": r.signals,
                "rejected_at": iso(r.rejected_at),
            }
            for r in rejected
        ],
        "ecosystem_signals": [
            {
                "url": s.url,
                "title": s.title,
                "signal_type": s.signal_type,
                "published_at": iso(s.published_at),
            }
            for s in signals
        ],
        "project_debug": [
            {
                "id": p.id,
                "name": p.name,
                "visible": p.visible,
                "confidence": p.confidence,
                "real_project_confidence": p.real_project_confidence,
                "signals": p.detection_signals,
                "stop_reasons": [STOP_LABELS.get(r, r) for r in p.stop_reasons],
            }
            for p in projects[-50:]
        ],
    }


def sector_stats(session, days=30):
    now = now_utc()
    projects = list(
        session.scalars(
            select(Project).where(Project.visible.is_(True), Project.first_seen >= now - timedelta(days=days))
        )
    )
    items = []
    for sector, label in SECTORS.items():
        members = [p for p in projects if sector in p.sectors]
        items.append(
            {
                "sector": sector,
                "label": label,
                "count": len(members),
                "today": sum(aware(p.first_seen) >= today_start(now) for p in members),
            }
        )
    return {
        "period_days": days,
        "total_projects": len(projects),
        "items": sorted(items, key=lambda i: (-i["count"], i["label"])),
    }


def evidence_json(project):
    return [
        {
            "id": e.id,
            "source_id": e.source_id,
            "url": e.url,
            "evidence_type": e.evidence_type,
            "label": EVIDENCE_LABELS.get(e.evidence_type, e.evidence_type),
            "confidence": e.confidence,
            "quote": e.quote,
            "notes": e.notes,
            "discovered_at": iso(e.discovered_at),
        }
        for e in project.evidence_records
    ]
