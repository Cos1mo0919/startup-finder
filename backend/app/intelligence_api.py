"""Read-only problem, idea, signal and opportunity views."""

from datetime import timedelta
from sqlalchemy import func, select
from .db import (Candidate, EcosystemSignal, Problem, ProblemEvidence, Project,
                 RegistrySource, Run, SchedulerCheckpoint, SolutionIdea)
from .dates import today_start
from .db import aware, now_utc
from .radar_api import iso
from .sectors import SECTORS


def problem_json(p, sources=0):
    return {
        "id": p.id, "title_uz": p.title_uz, "description_uz": p.description_uz,
        "scope": p.scope, "country": p.country, "region": p.region,
        "sector": p.sector, "affected_users": p.affected_users,
        "status": p.status, "confidence": p.confidence, "evidence_level": p.evidence_level,
        "scores": p.scores, "source_count": sources,
        "first_seen_at": iso(p.first_seen_at), "last_seen_at": iso(p.last_seen_at),
        "first_evidence_published_at": iso(p.first_evidence_published_at),
    }


def idea_json(i):
    return {key: getattr(i, key) for key in (
        "id", "problem_id", "idea_title", "idea_summary", "target_user",
        "proposed_solution", "current_alternatives", "why_current_alternatives_fail",
        "business_model_hypothesis", "mvp_hypothesis", "main_risks",
        "evidence_basis", "generated_by", "status", "opportunity_details"
    )} | {"created_at": iso(i.created_at)}


def signal_json(s):
    return {"url": s.url, "title": s.title, "signal_type": s.signal_type,
            "summary_uz": s.summary_uz or s.title,
            "why_it_matters_uz": s.why_it_matters_uz,
            "country": s.country, "region": s.region, "sector": s.sector,
            "confidence": s.confidence, "published_at": iso(s.published_at),
            "discovered_at": iso(s.discovered_at), "source_id": s.source_id}


def dashboard(session):
    now = now_utc()
    start = today_start(now)
    today_runs = list(session.scalars(select(Run).where(Run.started_at >= start)))
    return {
        "today": {
            "sources_checked": sum(r.counts.get("sources_checked", 0) for r in today_runs),
            "links_seen": sum(r.counts.get("candidates_found", 0) for r in today_runs),
            "projects": session.scalar(select(func.count()).select_from(Project).where(Project.publication_status == "PUBLISHED", Project.published_at >= start)),
            "problems": session.scalar(select(func.count()).select_from(Problem).where(Problem.first_seen_at >= start)),
            "ideas": session.scalar(select(func.count()).select_from(SolutionIdea).where(SolutionIdea.created_at >= start)),
            "signals": session.scalar(select(func.count()).select_from(EcosystemSignal).where(EcosystemSignal.discovered_at >= start)),
        },
        "total": {
            "projects": session.scalar(select(func.count()).select_from(Project).where(Project.publication_status == "PUBLISHED")),
            "problems": session.scalar(select(func.count()).select_from(Problem)),
            "ideas": session.scalar(select(func.count()).select_from(SolutionIdea)),
            "signals": session.scalar(select(func.count()).select_from(EcosystemSignal).where(EcosystemSignal.intelligence_status == "ACTIVE")),
            "candidates": session.scalar(select(func.count()).select_from(Candidate)),
            "sources": session.scalar(select(func.count()).select_from(RegistrySource)),
        },
        "strong_opportunities": [{"id": p.id, "name": p.name, "score": p.opportunity_score,
                                  "grade": p.opportunity_grade, "problem": p.problem_statement}
                                 for p in session.scalars(select(Project).where(
                                     Project.publication_status == "PUBLISHED", Project.opportunity_grade.in_(["A", "B"])
                                 ).order_by(Project.opportunity_score.desc()).limit(6))],
        "latest_projects": [{
            "id": p.id, "name": p.name, "problem": p.problem_statement,
            "solution": (p.content or {}).get("how_uz") or (p.content or {}).get("what_uz") or "",
            "affected_users": p.problem_subject or ", ".join(
                group for group in (p.content or {}).get("audience_groups", []) if isinstance(group, str)
            ),
            "problem_gate_status": p.problem_gate_status,
            "opportunity_score": p.opportunity_score,
            "opportunity_grade": p.opportunity_grade,
            "problem_score": (p.opportunity_details or {}).get("groups", {}).get("problem"),
            "market_score": (p.opportunity_details or {}).get("groups", {}).get("market"),
            "evidence_score": p.confidence,
            "country": p.country, "sector": p.primary_sector,
            "published_at": iso(p.published_at), "source_count": len(p.sources),
        } for p in session.scalars(select(Project).where(
            Project.publication_status == "PUBLISHED", Project.published_at >= now - timedelta(days=30)
        ).order_by(Project.published_at.desc()).limit(5))],
        "latest_problems": [problem_json(p, session.scalar(select(func.count(func.distinct(ProblemEvidence.source_url))).where(ProblemEvidence.problem_id == p.id))) for p in session.scalars(select(Problem).order_by(Problem.last_seen_at.desc()).limit(5))],
        "latest_ideas": [idea_json(i) for i in session.scalars(
            select(SolutionIdea).order_by(SolutionIdea.created_at.desc()).limit(5)
        )],
        "latest_signals": [signal_json(s) for s in session.scalars(select(EcosystemSignal).where(EcosystemSignal.intelligence_status == "ACTIVE").order_by(EcosystemSignal.discovered_at.desc()).limit(5))],
    }


def status_extra(session):
    checkpoints = list(session.scalars(select(SchedulerCheckpoint)))
    projects = list(session.scalars(select(Project)))
    visible = [p for p in projects if p.publication_status == "PUBLISHED"]
    scored = [p.opportunity_score for p in visible if p.opportunity_score is not None]
    evidence_levels = dict(session.execute(
        select(Problem.evidence_level, func.count()).group_by(Problem.evidence_level)
    ).all())
    rating_methods = {
        method: sum(p.content.get("analysis_mode") == method for p in visible)
        for method in ("extractive", "ai")
    }
    last_success = session.scalar(select(Run.finished_at).where(Run.status == "completed").order_by(Run.finished_at.desc()).limit(1))
    source_success = session.scalar(select(RegistrySource.last_success_at).where(RegistrySource.last_success_at.is_not(None)).order_by(RegistrySource.last_success_at.desc()).limit(1))
    processed_item = session.scalar(select(Candidate.updated_at).where(Candidate.status != "queued").order_by(Candidate.updated_at.desc()).limit(1))
    return {
        "intelligence_counts": dashboard(session)["total"],
        "publication_counts": {
            "total_project_records": len(projects),
            "verified_projects": sum(p.visible for p in projects),
            "analyzed_projects": sum(bool(p.visible and p.problem_gate_status == "PASS" and p.problem_statement and p.problem_subject and (p.content or {}).get("what_uz")) for p in projects),
            "published_projects": len(visible),
            "review_required": sum(p.publication_status == "REVIEW_REQUIRED" for p in projects),
            "archived_projects": sum(p.publication_status == "PUBLISHED" and aware(p.published_at) < today_start(now_utc()) for p in projects),
        },
        "entity_type_counts": dict(session.execute(select(Candidate.entity_type, func.count()).group_by(Candidate.entity_type)).all()),
        "problem_gate_counts": dict(session.execute(select(Project.problem_gate_status, func.count()).group_by(Project.problem_gate_status)).all()),
        "scoring_summary": {
            "scored": len(scored),
            "pending": sum(p.opportunity_grade == "PENDING" for p in visible),
            "rejected_by_stop_filter": sum(p.opportunity_grade == "REJECTED" for p in projects),
            "average_opportunity": round(sum(scored) / len(scored), 1) if scored else None,
            "problem_evidence_levels": evidence_levels,
            "rating_methods": rating_methods,
        },
        "last_successful_scan_at": iso(last_success),
        "last_successful_source_check_at": iso(source_success),
        "last_processed_item_at": iso(processed_item),
        "scan_checkpoints": [{"name": c.name, "last_attempt_at": iso(c.last_attempt_at),
                              "last_success_at": iso(c.last_success_at),
                              "last_processed_item_at": iso(c.last_processed_item_at),
                              "cursor": c.cursor} for c in checkpoints],
    }


def sector_intelligence(session):
    projects = list(session.scalars(select(Project).where(Project.publication_status == "PUBLISHED")))
    problems = list(session.scalars(select(Problem)))
    signals = list(session.scalars(select(EcosystemSignal).where(EcosystemSignal.intelligence_status == "ACTIVE")))
    result = []
    for key, label in SECTORS.items():
        ps = [p for p in projects if key in (p.sectors or [])]
        prs = [p for p in problems if p.sector == key]
        ss = [s for s in signals if s.sector == key]
        if not (ps or prs or ss):
            continue
        scored = [p.opportunity_score for p in ps if p.opportunity_score is not None]
        result.append({"sector": key, "label": label, "projects": len(ps),
                       "problems": len(prs), "signals": len(ss),
                       "average_opportunity": round(sum(scored) / len(scored), 1) if scored else None,
                       "sample_size": len(scored)})
    return sorted(result, key=lambda x: -(x["projects"] + x["problems"] + x["signals"]))
