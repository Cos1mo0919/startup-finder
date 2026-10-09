"""Continuous v3.1 project catalog discovery and bounded enrichment."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta
from time import monotonic, sleep
from uuid import uuid4

from sqlalchemy import func, or_, select, update

from .catalog import (CatalogClassifier, CatalogResult, ClassifierFailure,
                      deterministic_entry)
from .catalog_store import save_catalog_result
from .dates import parse_date
from .dates import TASHKENT
from .db import Candidate, Lease, Project, Run, aware, now_utc
from .network import FetchError, canonical_url
from .pipeline import Pipeline
from .schemas import Article

OBVIOUS_NOISE = re.compile(
    r"stipendiya|scholarship|стипенд|siyosiy tayinlov|political appointment|"
    r"вакансия|vakansiya|job opening|bo.sh ish o.rni|reklama|advertisement",
    re.I,
)


class CatalogPipeline(Pipeline):
    def __init__(self, settings, factory, discovery=None, classifier=None):
        super().__init__(settings, factory, discovery=discovery)
        self.classifier = classifier or CatalogClassifier(settings)
        self.trusted_path = settings.trusted_catalog_file

    def _classify(self, article):
        if OBVIOUS_NOISE.search(article.title):
            return CatalogResult("NOT_PROJECT", 0.95, reason="obvious_noise", analysis_method="deterministic")
        if self.settings.ai_key:
            return self.classifier.classify(article)
        try:
            entry = deterministic_entry(article, self.trusted_path)
        except ClassifierFailure as exc:
            return CatalogResult("NEEDS_EXTRACTION", 0.5, reason=str(exc), analysis_method="deterministic")
        if entry:
            return CatalogResult("PROJECT", entry.confidence, (entry,), analysis_method="deterministic")
        return CatalogResult("NEEDS_EXTRACTION", 0.5, reason="llm_unavailable", analysis_method="deterministic")

    def _enrich(self, now, counts, errors):
        if not self.settings.ai_key:
            return
        with self.factory() as session:
            projects = session.scalars(select(Project).where(
                Project.analysis_method == "deterministic", Project.score_pending.is_(True),
                or_(Project.reanalysis_next_at.is_(None), Project.reanalysis_next_at <= now),
            ).order_by(Project.first_seen).limit(self.settings.reanalysis_batch_size)).all()
            work = [(project.id, project.sources[0].url) for project in projects if project.sources]
        failures = 0
        for project_id, url in work:
            if failures >= self.settings.reanalysis_failure_limit:
                counts["reanalysis_circuit_open"] += 1
                break
            try:
                article = self.discovery.article(url)
                result = self.classifier.classify(article)
                with self.factory.begin() as session:
                    project = session.get(Project, project_id)
                    project.reanalysis_attempts += 1
                    project.reanalysis_next_at = now + timedelta(days=1)
                    if result.classification in ("PROJECT", "MULTI"):
                        save_catalog_result(session, article, result, now)
                        if project.analysis_method == "hybrid":
                            project.reanalysis_state = "completed"
                            counts["enriched"] += 1
                        else:
                            project.reanalysis_state = "review_required"
                    else:
                        save_catalog_result(session, article, result, now)
                        project.reanalysis_state = "review_required" if result.confidence >= 0.7 else "llm_disagrees"
            except FetchError as exc:
                with self.factory.begin() as session:
                    project = session.get(Project, project_id)
                    project.reanalysis_state = "source_unavailable"
                    project.reanalysis_attempts += 1
                    project.reanalysis_next_at = now + timedelta(days=1)
                counts["source_unavailable"] += 1
                errors.append({"source": url, "stage": "reanalysis", "code": str(exc)})
                failures += 1
            except (ClassifierFailure, ValueError) as exc:
                with self.factory.begin() as session:
                    project = session.get(Project, project_id)
                    project.reanalysis_state = "error"
                    project.reanalysis_attempts += 1
                    project.reanalysis_next_at = now + timedelta(hours=min(24, 2 ** project.reanalysis_attempts))
                errors.append({"source": url, "stage": "reanalysis", "code": str(exc)})
                failures += 1
            if self.settings.reanalysis_delay_seconds:
                sleep(self.settings.reanalysis_delay_seconds)

    def run(self, archive=False, discover=True, only_source=None, only_urls=None, force_sources=False, reanalyze=True):
        owner, now, began = str(uuid4()), now_utc(), monotonic()
        if not self.acquire(owner, now):
            return {"status": "busy"}
        counts = Counter({"sources_checked": 0, "candidates_found": 0, "new_candidates": 0,
                          "candidates": 0, "auto_published": 0, "review_required": 0,
                          "rejected": 0, "duplicates": 0, "enriched": 0,
                          "source_unavailable": 0, "reanalysis_circuit_open": 0})
        errors, yield_by_source = [], defaultdict(Counter)
        with self.factory.begin() as session:
            run = Run(started_at=now, status="running", counts={},
                      details={"mode": "catalog_archive" if archive else "catalog_fresh"})
            session.add(run)
            session.flush()
            run_id = run.id
        status = "failed"
        try:
            if only_source:
                self.discovery.allowed_source_ids = {only_source}
            self.discovery.force = force_sources
            links, source_errors, checked = self.discovery.discover(now, archive) if discover else ([], [], 0)
            if discover and not only_source and hasattr(self.discovery, "follow_events"):
                event_links, event_errors = self.discovery.follow_events(now)
                links.extend(event_links)
                source_errors.extend(event_errors)
            errors.extend(source_errors)
            counts["sources_checked"] = checked
            counts["candidates_found"] = len({canonical_url(item["url"]) for item in links})
            with self.factory.begin() as session:
                for item in links:
                    url = canonical_url(item["url"])
                    row = session.get(Candidate, url)
                    if row is None:
                        row = Candidate(url=url, article={"_queued": True, "_fetch_url": item["url"],
                                                           "_feed_date": item["published_at"].isoformat() if item.get("published_at") else None,
                                                           "_discovery_url": item.get("discovery_url"),
                                                           "_discovery_title": item.get("title", "")},
                                        status="queued", source_id=item.get("source_id"), origin=item.get("origin", "other"))
                        session.add(row)
                        counts["new_candidates"] += 1
                    elif item.get("discovery_url") and not (row.article or {}).get("discovery_url"):
                        row.article = {**(row.article or {}), "discovery_url": item["discovery_url"],
                                       "discovery_title": item.get("title", "")}
                    yield_by_source[item.get("source_id") or "unknown"]["fetched"] += 1
            with self.factory() as session:
                retry_due = Candidate.updated_at <= now - timedelta(hours=6)
                query = select(Candidate).where(or_(
                    Candidate.status == "queued",
                    (Candidate.status.in_(["pending", "review_required", "error"]) &
                     ((Candidate.processing_version < 7) |
                      ((Candidate.status == "error") & retry_due) |
                      (((Candidate.analysis_mode == "deterministic") | retry_due) if self.settings.ai_key else False))),
                ))
                if only_urls:
                    query = select(Candidate)
                if only_source:
                    query = query.where(Candidate.source_id == only_source)
                if only_urls:
                    query = query.where(Candidate.url.in_([canonical_url(url) for url in only_urls]))
                rows = session.scalars(query.order_by(Candidate.updated_at.desc()).limit(self.settings.max_candidates)).all()
                work = [(row.url, row.article or {}, row.source_id) for row in rows]
            for url, cached, source_id in work:
                counts["candidates"] += 1
                source_bucket = yield_by_source[source_id or "unknown"]
                source_bucket["processed"] += 1
                try:
                    if not cached.get("_queued") and cached.get("text"):
                        article = Article.model_validate(cached)
                    else:
                        article = self.discovery.article(cached.get("_fetch_url", url), parse_date(cached.get("_feed_date")))
                    article.discovery_url = article.discovery_url or cached.get("_discovery_url")
                    article.discovery_title = article.discovery_title or cached.get("_discovery_title", "")
                    article.source_id = source_id or article.source_id
                    window = getattr(self.discovery, "window", None)
                    if window and article.published_at and not window[0] <= aware(article.published_at).astimezone(TASHKENT).date() <= window[1]:
                        result = CatalogResult("NOT_PROJECT", 0.95, reason="outside_archive_window",
                                               analysis_method="deterministic")
                    else:
                        result = self._classify(article)
                    with self.factory.begin() as session:
                        candidate = session.get(Candidate, url)
                        candidate.article = {**article.model_dump(mode="json"),
                                             "_catalog_entries": [entry.model_dump(mode="json") for entry in result.entries]}
                        candidate.attempts += 1
                        candidate.updated_at = now
                        candidate.last_run_id = run_id
                        candidate.processing_version = 7
                        candidate.analysis_mode = result.analysis_method
                        outcomes = save_catalog_result(session, article, result, now)
                    for key, value in outcomes.items():
                        counts[key] += value
                        source_bucket[key] += value
                except FetchError as exc:
                    with self.factory.begin() as session:
                        candidate = session.get(Candidate, url)
                        candidate.status, candidate.reason = "error", str(exc)
                        candidate.attempts += 1
                        candidate.processing_version = 7
                        candidate.updated_at = now
                    errors.append({"source": url, "stage": "fetch", "code": str(exc)})
                    source_bucket["errors"] += 1
                except (ClassifierFailure, ValueError) as exc:
                    reason = str(exc)
                    with self.factory.begin() as session:
                        candidate = session.get(Candidate, url)
                        candidate.status, candidate.reason = "review_required", reason
                        candidate.analysis_mode = "llm" if self.settings.ai_key else "deterministic"
                        candidate.processing_version = 7
                        candidate.attempts += 1
                        candidate.updated_at = now
                    counts["review_required"] += 1
                    source_bucket["review_required"] += 1
            if reanalyze:
                self._enrich(now, counts, errors)
            status = "partial" if errors else "completed"
        except Exception:
            status = "failed"
            errors.append({"source": "pipeline", "stage": "catalog", "code": "catalog_run_failed"})
            raise
        finally:
            with self.factory.begin() as session:
                run = session.get(Run, run_id)
                run.finished_at, run.status = now_utc(), status
                run.counts = dict(counts)
                run.errors = errors[:100]
                run.details = {"mode": "catalog_archive" if archive else "catalog_fresh",
                               "window": [part.isoformat() for part in self.discovery.window] if getattr(self.discovery, "window", None) else [],
                               "coverage": getattr(self.discovery, "archive_coverage", []),
                               "limits": {"max_candidates": self.settings.max_candidates,
                                          "archive_pages": self.settings.archive_pages},
                               "source_yield": {key: dict(value) for key, value in yield_by_source.items()},
                               "remaining_queue": session.scalar(select(func.count()).select_from(Candidate).where(Candidate.status.in_(["queued", "pending", "review_required"])))}
                run.duration_seconds = round(monotonic() - began, 2)
                session.execute(update(Lease).where(Lease.name == "pipeline", Lease.owner == owner)
                                .values(owner="", expires_at=now_utc()))
        return {"id": run_id, "status": status, "counts": dict(counts), "errors": errors[:100],
                "details": {"source_yield": {key: dict(value) for key, value in yield_by_source.items()}}}
