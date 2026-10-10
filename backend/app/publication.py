"""Conservative, idempotent public publication gate.

Evidence verification and product analysis are separate. Legacy ``visible`` is
retained for diagnostics; normal public queries use ``publication_status``.
"""

import json
from functools import lru_cache

from .config import ROOT
from .db import Project

FATAL_REASONS = {"not_project", "not_a_project", "idea_list", "spam", "ecosystem_signal", "minor_feature", "invalid_date"}


@lru_cache(maxsize=1)
def manual_source_reviews() -> dict[str, str]:
    review_file = ROOT / "config/publication_review.json"
    if not review_file.exists():
        return {}
    return {item["url"]: item["reason"] for item in
            json.loads(review_file.read_text()).get("source_reviews", [])}


def solution_text(project: Project) -> str:
    content = project.content or {}
    return (content.get("how_uz") or content.get("what_uz") or "").strip()


def lifecycle_stage(project: Project) -> str:
    """Furthest quality gate passed, independently of review disposition."""
    if not project.sources or not project.visible:
        return "DISCOVERED"
    if (project.problem_gate_status == "PASS" and project.problem_statement.strip()
            and project.problem_subject.strip() and solution_text(project)):
        return "PUBLISHED" if project.publication_status == "PUBLISHED" else "ANALYZED"
    return "VERIFIED_PROJECT"


def publication_state(project: Project) -> tuple[str, str]:
    reasons = set(project.stop_reasons or [])
    if reasons & FATAL_REASONS or project.problem_gate_status == "REJECT":
        return "REJECTED", next(iter(sorted(reasons & FATAL_REASONS)), project.problem_gate_reason or "no_meaningful_problem")
    if not project.sources:
        return "DISCOVERED", "missing_source"
    if not project.visible:
        return "REVIEW_REQUIRED", (project.stop_reasons or ["insufficient_evidence"])[0]
    if project.problem_gate_status != "PASS" or not project.problem_statement.strip():
        return "REVIEW_REQUIRED", project.problem_gate_reason or "pending_problem_analysis"
    if not project.problem_subject.strip():
        return "REVIEW_REQUIRED", "missing_target_user"
    if not solution_text(project):
        return "REVIEW_REQUIRED", "missing_solution"
    if "to‘liq tarjima uchun ai tahlili kerak" in solution_text(project).lower():
        return "REVIEW_REQUIRED", "needs_translation"
    if not project.published_at:
        return "REVIEW_REQUIRED", "unknown_publication_date"
    if not (project.content or {}).get("facts"):
        return "REVIEW_REQUIRED", "insufficient_evidence"
    return "PUBLISHED", "source_backed_problem_and_solution"


def refresh_publication(project: Project) -> str:
    project.publication_status, project.publication_reason = publication_state(project)
    return project.publication_status


def synchronize_candidate_publication(factory) -> None:
    """Reconcile candidate labels with the canonical public project state.

    A historical candidate is upgraded from IGNORE only when a real, published
    project is linked to its exact source. Candidate status alone proves nothing.
    """
    from sqlalchemy import select
    from .db import Candidate, Source
    from .catalog_store import history
    from .db import now_utc

    manual_reviews = manual_source_reviews()
    old_gate_reasons = {"pending_problem_analysis", "missing_target_user", "missing_solution",
                        "insufficient_evidence", "needs_translation", "unknown_publication_date"}
    with factory.begin() as session:
        for candidate in session.scalars(select(Candidate).where(Candidate.status.in_(["published", "review_required"]))):
            original_project_ids = set(candidate.project_ids or [])
            projects = [session.get(Project, pid) for pid in candidate.project_ids or []]
            projects.extend(session.scalars(select(Project).join(Source).where(Source.url == candidate.url)))
            projects = [project for project in projects if project is not None]
            if projects:
                candidate.project_ids = list(dict.fromkeys([*(candidate.project_ids or []), *(p.id for p in projects)]))
            manual_reason = manual_reviews.get(candidate.url)
            if manual_reason:
                if candidate.entity_type != "IGNORE":
                    candidate.classification_history = history(candidate.classification_history,
                        candidate.entity_type, "manual", "superseded_entity_type", now_utc())
                    candidate.entity_type = "IGNORE"
                if candidate.status != "review_required" or candidate.reason != manual_reason:
                    candidate.status, candidate.reason = "review_required", manual_reason
                    candidate.status_history = history(candidate.status_history, "REVIEW_REQUIRED", "manual",
                                                       manual_reason, now_utc())
                for project in projects:
                    if project.publication_status == "PUBLISHED" and len(project.sources) == 1:
                        project.publication_status = "REVIEW_REQUIRED"
                        project.publication_method = "admin"
                        project.publication_reason = project.review_reason = manual_reason
                        project.classification_history = history(project.classification_history,
                                                                 "NOT_PROJECT", "manual", manual_reason, now_utc())
                        project.status_history = history(project.status_history, "REVIEW_REQUIRED",
                                                         "manual", manual_reason, now_utc())
                continue
            for project in projects:
                if (candidate.status != "published" or project.publication_status != "REVIEW_REQUIRED"
                        or project.publication_reason not in old_gate_reasons or not project.visible
                        or project.id not in original_project_ids
                        or project.stop_reasons or project.publication_method == "admin"
                        or not project.name.strip() or not (project.short_description or (project.content or {}).get("summary_uz"))
                        or not any(source.url == candidate.url for source in project.sources)):
                    continue
                catalog_validated = (project.analysis_method in {"llm", "deterministic", "hybrid"}
                    and candidate.detector_result in {"PROJECT", "MULTI"}
                    and (candidate.classification_confidence or 0) >= 0.7)
                historical_validated = (project.analysis_method == "legacy" and candidate.analysis_mode == "extractive"
                    and bool(project.creator or project.organization) and bool((project.content or {}).get("facts"))
                    and project.confidence >= 5)
                if catalog_validated or historical_validated:
                    project.publication_status = "PUBLISHED"
                    project.publication_reason = "recovered_from_legacy_problem_gate"
                    project.status_history = history(project.status_history, "PUBLISHED", "reconciliation",
                                                     project.publication_reason, now_utc())
            published = [project for project in projects if project.publication_status == "PUBLISHED"
                         and project.name.strip() and (project.short_description or (project.content or {}).get("summary_uz"))
                         and any(source.url == candidate.url for source in project.sources)]
            latest_not_project = candidate.detector_result == "NOT_PROJECT" and (candidate.classification_confidence or 0) >= 0.7
            if latest_not_project:
                for project in published:
                    if len(project.sources) == 1 and project.publication_method != "admin":
                        project.publication_status = "REVIEW_REQUIRED"
                        project.visible = False
                        project.publication_reason = project.review_reason = "llm_reclassified_not_project"
                        project.status_history = history(project.status_history, "REVIEW_REQUIRED",
                                                         "reconciliation", project.review_reason, now_utc())
            if candidate.status == "published" and published and not latest_not_project:
                if candidate.entity_type != "PROJECT":
                    candidate.classification_history = history(candidate.classification_history,
                        candidate.entity_type, "legacy", "superseded_entity_type", now_utc())
                    candidate.entity_type = "PROJECT"
            elif candidate.status == "published":
                candidate.status = "review_required"
                candidate.reason = "not_project_classification" if latest_not_project else "no_canonical_published_project"
                candidate.status_history = history(candidate.status_history, "REVIEW_REQUIRED", "reconciliation",
                                                   candidate.reason, now_utc())
        for project in session.scalars(select(Project)):
            # Legacy visible is a compatibility mirror, never the public gate.
            project.visible = project.publication_status == "PUBLISHED"
