"""Conservative, idempotent public publication gate.

Evidence verification and product analysis are separate. Legacy ``visible`` is
retained for diagnostics; normal public queries use ``publication_status``.
"""

from .db import Project

FATAL_REASONS = {"not_project", "not_a_project", "idea_list", "spam", "ecosystem_signal", "minor_feature", "invalid_date"}


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
    """Reconcile legacy candidate labels after existing projects are audited."""
    from sqlalchemy import select
    from .db import Candidate, Source

    with factory.begin() as session:
        for candidate in session.scalars(select(Candidate).where(Candidate.status.in_(["published", "review_required"]))):
            projects = [session.get(Project, pid) for pid in candidate.project_ids or []]
            projects.extend(session.scalars(select(Project).join(Source).where(Source.url == candidate.url)))
            projects = [project for project in projects if project is not None]
            if not projects:
                continue
            candidate.project_ids = list(dict.fromkeys([*(candidate.project_ids or []), *(project.id for project in projects)]))
            if any(project.publication_status == "PUBLISHED" for project in projects):
                candidate.status, candidate.reason = "published", ""
            elif any(project.publication_status == "REVIEW_REQUIRED" for project in projects):
                candidate.status = "review_required"
                candidate.reason = next(project.publication_reason for project in projects if project.publication_status == "REVIEW_REQUIRED")
