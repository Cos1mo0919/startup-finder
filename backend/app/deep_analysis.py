"""Optional, post-publication 15-criterion evaluation with verified weights only."""

from __future__ import annotations

from .writer import serialized_worker

import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from .config import ROOT
from .db import Project, ProjectDeepAnalysis, now_utc, aware
from .intelligence import CRITERIA
from .llm_service import LLMService, LLMUnavailable

CRITERION_NAMES = tuple(name for group in CRITERIA.values() for name in group)
WEIGHTS_PATH = ROOT / "config/deep_score_weights.json"
PROMPT_PATH = ROOT / "config/prompts/deep_analysis_v1.txt"


def validate_criteria(payload, source_urls):
    if not isinstance(payload, dict) or not isinstance(payload.get("criteria"), dict):
        raise ValueError("invalid_deep_schema")
    result = {}
    for name, value in payload["criteria"].items():
        if name not in CRITERION_NAMES or not isinstance(value, dict):
            raise ValueError("invalid_deep_schema")
        score = value.get("score")
        refs = value.get("evidence_refs")
        if (type(score) is not int or not 1 <= score <= 5 or
                not isinstance(value.get("reason"), str) or not value["reason"].strip() or
                not isinstance(refs, list) or not refs or not all(ref in source_urls for ref in refs)):
            raise ValueError("invalid_deep_evidence")
        result[name] = {"score": score, "reason": value["reason"].strip()[:500],
                        "evidence_refs": list(dict.fromkeys(refs))}
    return result


def weighted_score(criteria, path: Path = WEIGHTS_PATH):
    config = json.loads(path.read_text())
    if not config.get("validated"):
        return None, config["version"]
    weights = config.get("weights")
    if (set(weights or {}) != set(CRITERION_NAMES) or
            any(type(value) not in (int, float) or value <= 0 for value in weights.values()) or
            abs(sum(weights.values()) - 1.0) > 0.000001):
        raise ValueError("invalid_deep_weights")
    if set(criteria) != set(CRITERION_NAMES):
        return None, config["version"]
    return round(sum(criteria[name]["score"] * weights[name] for name in CRITERION_NAMES) * 20, 1), config["version"]




@serialized_worker
def deep_analysis_once(settings, factory, service=None, limit=5):
    """Analyze published rows only; a failure cannot change publication status."""
    service = service or LLMService(settings, factory)
    if not service.available:
        return {"status": "llm_unavailable", "analyzed": 0, "pending": 0}
    now = now_utc()
    with factory() as session:
        rows = session.scalars(select(Project).where(Project.publication_status == "PUBLISHED")
                               .order_by(Project.first_seen).limit(500)).all()
        work = []
        for project in rows:
            existing = session.get(ProjectDeepAnalysis, project.id)
            if existing and (existing.status == "completed" or
                             (existing.next_attempt_at and aware(existing.next_attempt_at) > now)):
                continue
            work.append((project.id, project.name, project.short_description,
                         [(source.url, source.quotes) for source in project.sources]))
            if len(work) >= limit:
                break
    completed, pending = 0, 0
    for project_id, name, description, sources in work:
        urls = {url for url, _ in sources}
        # Only cached source excerpts are sent; absent evidence stays unknown.
        context = json.dumps({"name": name, "description": description,
                              "sources": [{"url": url, "excerpts": quotes} for url, quotes in sources]},
                             ensure_ascii=False)[:14000]
        try:
            analysis = service.analyze_json(PROMPT_PATH.read_text(), context,
                                            lambda payload: validate_criteria(payload, urls))
            score, version = weighted_score(analysis.result)
            with factory.begin() as session:
                row = session.get(ProjectDeepAnalysis, project_id)
                if row is None:
                    row = ProjectDeepAnalysis(project_id=project_id)
                    session.add(row)
                row.criteria = analysis.result
                row.weighted_score = score
                row.weights_version = version
                row.provider, row.model = analysis.provider, analysis.model
                row.status = "completed" if analysis.result else "partial"
                row.error = "" if analysis.result else "insufficient_evidence"
                row.attempts = (row.attempts or 0) + 1
                row.analyzed_at = now
                row.next_attempt_at = now + timedelta(days=30 if analysis.result else 1)
            completed += int(bool(analysis.result))
            pending += int(not analysis.result)
        except (LLMUnavailable, ValueError) as exc:
            with factory.begin() as session:
                row = session.get(ProjectDeepAnalysis, project_id)
                if row is None:
                    row = ProjectDeepAnalysis(project_id=project_id)
                    session.add(row)
                row.status, row.error = "partial", str(exc)[:100]
                row.attempts = (row.attempts or 0) + 1
                row.next_attempt_at = now + timedelta(hours=6)
            pending += 1
    return {"status": "completed" if not pending else "partial", "analyzed": completed, "pending": pending}
