"""Idempotent catalog persistence with append-only decision histories."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from sqlalchemy import select

from .catalog import CatalogEntry, CatalogResult, catalog_score, decision, duplicate_decision
from .db import Candidate, Project, ProjectEvidence, Source, now_utc
from .detection import normalize
from .network import canonical_url


def history(previous: list | None, value: str, method: str, reason: str, when: datetime) -> list:
    item = {"timestamp": when.isoformat(), "value": value, "analysis_method": method, "reason": reason}
    return [*(previous or []), item]


def _description(entry: CatalogEntry, method: str) -> str:
    return entry.description_uz.strip()


def save_catalog_result(session, article, result: CatalogResult, when=None) -> dict:
    when = when or now_utc()
    url = canonical_url(article.url)
    candidate = session.get(Candidate, url)
    if candidate is None:
        candidate = Candidate(url=url, article=article.model_dump(mode="json"), source_id=article.source_id)
        session.add(candidate)
    counts = {"auto_published": 0, "review_required": 0, "rejected": 0, "duplicates": 0}
    candidate.classification_confidence = result.confidence
    candidate.detector_result = result.classification
    candidate.classification_history = history(candidate.classification_history, result.classification, result.analysis_method, result.reason, when)
    if not result.entries:
        if result.classification == "NOT_PROJECT" and result.analysis_method == "llm":
            linked = [session.get(Project, project_id) for project_id in candidate.project_ids or []]
            deterministic = [project for project in linked if project and project.analysis_method == "deterministic"]
            for project in deterministic:
                project.classification_history = history(project.classification_history, "NOT_PROJECT", "llm", result.reason, when)
                if result.confidence >= 0.7:
                    project.publication_status = "REVIEW_REQUIRED"
                    project.review_reason = project.publication_reason = "llm_reclassified_not_project"
                    project.status_history = history(project.status_history, "REVIEW_REQUIRED", "llm", project.review_reason, when)
                else:
                    project.review_reason = "llm_disagrees"
            if deterministic:
                candidate.status = "review_required" if result.confidence >= 0.7 else "published"
                candidate.reason = "llm_reclassified_not_project" if result.confidence >= 0.7 else "llm_disagrees"
                candidate.status_history = history(candidate.status_history, candidate.status.upper(), "llm", candidate.reason, when)
                counts["review_required" if result.confidence >= 0.7 else "duplicates"] += 1
                return counts
        state, reason = decision(result)
        candidate.status = "rejected" if state == "REJECTED" else "review_required"
        candidate.reason = reason
        candidate.status_history = history(candidate.status_history, state, result.analysis_method, reason, when)
        counts["rejected" if state == "REJECTED" else "review_required"] += 1
        return counts
    for entry in result.entries:
        state, reason = decision(result, entry)
        project, possible = duplicate_decision(session, entry, url)
        if possible and project is None:
            state, reason = "REVIEW_REQUIRED", "possible_duplicate"
        if project is not None:
            counts["duplicates"] += 1
            if project.publication_status == "PUBLISHED" and state == "REVIEW_REQUIRED":
                state, reason = "AUTO_PUBLISHED", "existing_published_project"
        if project is None and state == "REJECTED":
            counts["rejected"] += 1
            candidate.reason = reason
            continue
        if project is None and state == "REVIEW_REQUIRED":
            counts["review_required"] += 1
            candidate.reason = reason
            continue
        created = project is None
        description = _description(entry, result.analysis_method)
        if created:
            project = Project(
                name=entry.name, normalized_project_name=normalize(entry.name),
                creator=entry.creator or "", organization="", country=entry.country or "",
                city="", event="", main_url=entry.official_url,
                fingerprint=sha256(f"{normalize(entry.name)}|{normalize(entry.creator or '')}|{normalize(entry.country or '')}".encode()).hexdigest(),
                aliases=entry.aliases, first_seen=when, last_seen=when,
                published_at=article.published_at or when, category="other", audience="unknown",
                content={"summary_uz": description, "what_uz": description,
                         "how_uz": "", "facts": [], "analysis_mode": result.analysis_method},
                images=[{"url": article.image_url, "source_url": article.url, "publisher": article.publisher}]
                if article.image_url else [],
                rating=0, confidence=0, rating_components={}, confidence_components={},
                primary_sector="other", sectors=[], visible=True, stop_reasons=[],
                detection_signals=[], real_project_confidence=0,
                publication_status="DISCOVERED", publication_reason="",
            )
            session.add(project)
            session.flush()
        previous_status = project.publication_status
        if entry.name != project.name and normalize(entry.name) != project.normalized_project_name:
            project.aliases = list(dict.fromkeys([*(project.aliases or []), entry.name]))
        project.last_seen = when
        if not project.creator and entry.creator:
            project.creator = entry.creator
        if not project.country and entry.country:
            project.country = entry.country
        if not project.main_url and entry.official_url:
            project.main_url = entry.official_url
        if not project.short_description or (result.analysis_method == "llm" and project.analysis_method == "deterministic"):
            project.short_description = description
            project.content = {**(project.content or {}), "summary_uz": description, "what_uz": description,
                               "analysis_mode": result.analysis_method}
        project.analysis_method = (
            "hybrid" if result.analysis_method == "llm" and project.analysis_method == "deterministic"
            else result.analysis_method
        )
        project.description_needs_translation = result.analysis_method == "deterministic"
        project.publication_method = "deterministic" if result.analysis_method == "deterministic" else "llm"
        project.discovery_source_url = project.discovery_source_url or article.discovery_url or url
        project.date_estimated = article.published_at is None if created else project.date_estimated
        project.publication_excerpt = project.publication_excerpt or article.text[:1500]
        project.catalog_score = catalog_score(entry)
        project.evidence_count = (2 + int(entry.score_evidence.novelty) + int(entry.score_evidence.potential)
                                  if entry.score_evidence else 0)
        project.classification_confidence = entry.confidence
        project.catalog_scores = entry.scores.model_dump() if entry.scores else {}
        project.catalog_score_reasons = entry.score_reasons
        project.score_evidence = entry.score_evidence.model_dump() if entry.score_evidence else {}
        project.score_pending = entry.scores is None
        project.primary_sector = entry.sector
        project.sector_method = ("llm" if result.analysis_method == "llm" else
                                 "adapter" if article.structured_category else "keyword")
        project.project_type = entry.project_type
        project.project_type_method = "llm" if result.analysis_method == "llm" else "source_context"
        project.project_stage = entry.stage
        project.publication_status = "PUBLISHED" if state == "AUTO_PUBLISHED" else state
        project.publication_reason = reason
        project.review_reason = reason if state == "REVIEW_REQUIRED" else ""
        project.classification_history = history(project.classification_history, "PROJECT", result.analysis_method, reason, when)
        if created or previous_status != project.publication_status:
            project.status_history = history(project.status_history, state, result.analysis_method, reason, when)
        source = session.scalar(select(Source).where(Source.project_id == project.id, Source.url == url))
        if source is None:
            project.sources.append(Source(url=url, publisher=article.publisher, kind=article.kind,
                                          source_id=article.source_id, published_at=article.published_at or when,
                                          retrieved_at=when, quotes=[project.publication_excerpt]))
        if created or not any(e.url == url and e.quote == project.publication_excerpt for e in project.evidence_records):
            project.evidence_records.append(ProjectEvidence(url=url, evidence_type="project_exists",
                quote=project.publication_excerpt, source_id=article.source_id,
                confidence=entry.confidence, discovered_at=when,
                notes="Stored source excerpt used for catalog publication"))
        if article.image_url and not any(i.get("url") == article.image_url for i in project.images):
            project.images = [*project.images, {"url": article.image_url, "source_url": url, "publisher": article.publisher}][:5]
        candidate.project_ids = list(dict.fromkeys([*(candidate.project_ids or []), project.id]))
        candidate.reason = reason
        counts["auto_published" if state == "AUTO_PUBLISHED" and previous_status != "PUBLISHED" else "review_required" if state == "REVIEW_REQUIRED" else "duplicates"] += 1
    if counts["auto_published"]:
        candidate.status, candidate.reason = "published", ""
    elif counts["review_required"]:
        candidate.status = "review_required"
    elif counts["rejected"]:
        candidate.status = "rejected"
    else:
        candidate.status, candidate.reason = "published", "duplicate"
    candidate.status_history = history(candidate.status_history, candidate.status.upper(), result.analysis_method, candidate.reason, when)
    return counts
