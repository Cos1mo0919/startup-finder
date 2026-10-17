"""Continuous v3.1 project catalog discovery and bounded enrichment."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta
from time import monotonic, sleep
from uuid import uuid4

from sqlalchemy import case, func, literal, or_, select

from .catalog import (CatalogEntry, CatalogResult, ClassifierFailure,
                      deterministic_entry)
from .catalog_store import history, save_catalog_result
from .llm_service import LLMService, LLMUnavailable, PROMPT_VERSION
from .raw_discovery import cheap_decision, ingest_raw, record_transition
from .dates import parse_date
from .dates import TASHKENT
from .db import Candidate, Project, RawDiscovery, RegistrySource, Run, aware, now_utc
from .network import CandidateTimeout, FetchError, canonical_url
from .pipeline import Pipeline
from .schemas import Article
from .free_budget import BudgetStop

OBVIOUS_NOISE = re.compile(
    r"stipendiya|scholarship|стипенд|siyosiy tayinlov|political appointment|"
    r"вакансия|vakansiya|job opening|bo.sh ish o.rni|reklama|advertisement",
    re.I,
)


class CatalogPipeline(Pipeline):
    def __init__(self, settings, factory, discovery=None, classifier=None, llm_service=None):
        super().__init__(settings, factory, discovery=discovery)
        self.classifier = classifier
        self.llm_service = llm_service if llm_service is not None else (None if classifier else LLMService(settings, factory))
        self.last_llm_analysis = None
        self.trusted_path = settings.trusted_catalog_file

    def _classify(self, article):
        self.last_llm_analysis = None
        llm_attempted = False
        if self.llm_service:
            self.llm_service.last_attempt_count = 0
        if OBVIOUS_NOISE.search(article.title) and not re.search(
            r"\b(startup|startap|project|loyiha|platform|app|prototype|prototip|product|ilova)\b",
            article.title, re.I,
        ):
            return CatalogResult("NOT_PROJECT", 0.95, reason="obvious_noise", analysis_method="deterministic")
        if article.source_id == "show-hn-rss" and len(re.findall(r"\b[\w-]+\b", article.text)) < 50:
            return CatalogResult("NEEDS_EXTRACTION", 0.5, reason="source_excerpt_insufficient",
                                 analysis_method="deterministic")
        if self.classifier and self.settings.ai_key:
            return self.classifier.classify(article)
        if self.llm_service and self.llm_service.available:
            try:
                self.last_llm_analysis = self.llm_service.analyze_source(article)
                return self.last_llm_analysis.result
            except LLMUnavailable:
                llm_attempted = True
        if self.llm_service and not llm_attempted and not self.llm_service.available:
            self.llm_service.record_unavailable()
        try:
            entry = deterministic_entry(article, self.trusted_path)
        except ClassifierFailure as exc:
            return CatalogResult("NEEDS_EXTRACTION", 0.5, reason=str(exc), analysis_method="deterministic")
        if entry:
            return CatalogResult("PROJECT", entry.confidence, (entry,), analysis_method="deterministic")
        return CatalogResult("NEEDS_EXTRACTION", 0.5, reason="llm_unavailable",
                             analysis_method="llm_failed" if llm_attempted else "deterministic")

    @staticmethod
    def _diagnostics():
        from .telemetry import ACTIVE_TRACE
        trace = ACTIVE_TRACE.get()
        return {key: value for key, value in (trace or {}).items() if key not in {"deadline", "_spans"}}

    def _enrich(self, now, counts, errors):
        if not (self.settings.ai_key and self.classifier) and not (self.llm_service and self.llm_service.available):
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
                result = self.classifier.classify(article) if self.classifier else self.llm_service.analyze_source(article).result
                with self.factory.begin() as session:
                    project = session.get(Project, project_id)
                    project.reanalysis_attempts += 1
                    project.reanalysis_next_at = now + timedelta(days=1)
                    if result.classification in ("PROJECT", "MULTI"):
                        save_catalog_result(session, article, result, now, self.settings)
                        if project.analysis_method == "hybrid":
                            project.reanalysis_state = "completed"
                            counts["enriched"] += 1
                        else:
                            project.reanalysis_state = "review_required"
                    else:
                        save_catalog_result(session, article, result, now, self.settings)
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
            except (ClassifierFailure, LLMUnavailable, ValueError) as exc:
                with self.factory.begin() as session:
                    project = session.get(Project, project_id)
                    project.reanalysis_state = "error"
                    project.reanalysis_attempts += 1
                    project.reanalysis_next_at = now + timedelta(hours=min(24, 2 ** project.reanalysis_attempts))
                errors.append({"source": url, "stage": "reanalysis", "code": str(exc)})
                failures += 1
            if self.settings.reanalysis_delay_seconds:
                sleep(self.settings.reanalysis_delay_seconds)

    def run(self, archive=False, discover=True, only_source=None, only_urls=None,
            force_sources=False, reanalyze=True, process=True, review_only=False):
        from .daily import DailyLimitReached, today_stats
        owner, now, began = str(uuid4()), now_utc(), monotonic()
        if not self.acquire(owner, now):
            return {"status": "busy"}
        counts = Counter({"sources_checked": 0, "candidates_found": 0, "new_candidates": 0,
                          "raw_discoveries": 0, "pre_filtered": 0, "project_candidates": 0,
                          "recovered_window_rejections": 0,
                          "provider_circuit_open": 0,
                          "candidates": 0, "auto_published": 0, "review_required": 0,
                          "rejected": 0, "duplicates": 0, "enriched": 0,
                          "source_unavailable": 0, "reanalysis_circuit_open": 0})
        errors, yield_by_source = [], defaultdict(Counter)
        status, stop_reason, run_id, report_details = "failed", "", None, {}
        try:
            with self.factory.begin() as session:
                run = Run(started_at=now, status="running", counts={},
                          details={"mode": "catalog_archive" if archive else "catalog_fresh"})
                session.add(run)
                session.flush()
                run_id = run.id
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
            archive_window = getattr(self.discovery, "window", None) if archive else None
            scope = [part.isoformat() for part in archive_window] if archive_window else []
            with self.factory() as session:
                if discover and not archive:
                    old_window = session.scalars(select(Candidate).where(
                        Candidate.status == "rejected", Candidate.reason == "outside_archive_window")
                        .order_by(Candidate.updated_at).limit(self.settings.max_candidates)).all()
                    for row in old_window:
                        published = parse_date((row.article or {}).get("published_at"))
                        if published and now - timedelta(days=30) <= aware(published) <= now:
                            row.status, row.reason, row.updated_at = "queued", "", now
                            counts["recovered_window_rejections"] += 1
                for index, item in enumerate(links):
                    if index and index % 250 == 0:
                        # Release SQLite's writer lock during large archive imports.
                        # Committed chunks remain safe to revisit after interruption.
                        session.commit()
                    url = canonical_url(item["url"])
                    source_id = item.get("source_id") or "event_discovery"
                    source = session.get(RegistrySource, item.get("source_id")) if item.get("source_id") else None
                    raw, created = ingest_raw(session, source_adapter=source_id, source_url=url,
                                              source_name=source.name if source else source_id,
                                              source_type=source.source_type if source else "event",
                                              page_type=(source.options or {}).get("page_type", "") if source else "",
                                              title=item.get("title", ""), publication_date=item.get("published_at"),
                                              raw_payload={"discovery_url": item.get("discovery_url"),
                                                           "query": item.get("query"), "origin": item.get("origin")})
                    if created:
                        counts["raw_discoveries"] += 1
                        yield_by_source[source_id]["raw_discoveries"] += 1
                    if raw.source_url != url:
                        counts["duplicates"] += 1
                        continue
                    row = session.get(Candidate, url)
                    if row is None:
                        row = Candidate(url=url, article={"_queued": True, "_fetch_url": item["url"],
                                                           "_feed_date": item["published_at"].isoformat() if item.get("published_at") else None,
                                                           "_discovery_url": item.get("discovery_url"),
                                                           "_discovery_title": item.get("title", "")},
                                        status="queued", source_id=item.get("source_id"), origin=item.get("origin", "other"),
                                        archive_scope=scope)
                        session.add(row)
                        counts["new_candidates"] += 1
                    elif scope and row.status in {"queued", "pending", "review_required"}:
                        hint = item.get("published_at")
                        dated = ((hint and scope[0] <= str(hint)[:10] <= scope[1]) or
                                 f"/{scope[0][:4]}/" in url)
                        if not row.archive_scope or dated:
                            row.archive_scope = scope
                    elif created and row.status in {"published", "rejected"}:
                        record_transition(raw, "processed" if row.status == "published" else "rejected",
                                          row.reason or "previously_processed", (row.project_ids or [None])[0], now)
                    elif item.get("discovery_url") and not (row.article or {}).get("discovery_url"):
                        row.article = {**(row.article or {}), "discovery_url": item["discovery_url"],
                                       "discovery_title": item.get("title", "")}
                    yield_by_source[item.get("source_id") or "unknown"]["fetched"] += 1
                session.commit()
                # Telegram and future adapters may insert raw rows independently
                # of web discovery. Materialize a Candidate without losing payload.
                pending_raw = select(RawDiscovery).where(RawDiscovery.status == "pending")
                if only_urls:
                    pending_raw = pending_raw.where(RawDiscovery.source_url.in_([canonical_url(url) for url in only_urls]))
                if only_source:
                    pending_raw = pending_raw.where(RawDiscovery.source_adapter == only_source)
                if not process:
                    pending_raw = pending_raw.where(RawDiscovery.id == -1)
                for raw in session.scalars(pending_raw.order_by(RawDiscovery.discovered_at)
                                           .limit(self.settings.max_candidates)):
                    existing = session.get(Candidate, raw.source_url)
                    if existing and existing.status in {"event", "ecosystem", "problem", "rejected", "published"}:
                        record_transition(raw, "rejected" if existing.status == "rejected" else "processed",
                                          f"legacy_{existing.status}", (existing.project_ids or [None])[0], now)
                    elif existing is None:
                        session.add(Candidate(url=raw.source_url,
                                              article={"_queued": True, "_fetch_url": raw.source_url,
                                                       "_feed_date": raw.publication_date.isoformat() if raw.publication_date else None,
                                                       "_raw_id": raw.id}, status="queued",
                                              source_id=raw.source_adapter if session.get(RegistrySource, raw.source_adapter) else None,
                                              origin=raw.source_type or "other"))
                        counts["new_candidates"] += 1
                session.commit()
            with self.factory() as session:
                daily = today_stats(session, self.settings, now)
                if daily["published"] >= daily["limit"]:
                    process = False
                    stop_reason = "daily_publish_limit_reached"
                elif not process:
                    stop_reason = "processing_disabled"
                retry_due = Candidate.updated_at <= now - timedelta(hours=6)
                llm_ready = bool((self.classifier and self.settings.ai_key) or
                                 (self.llm_service and self.llm_service.available))
                query = select(Candidate).where(or_(
                    Candidate.status == "queued",
                    (Candidate.status.in_(["pending", "review_required", "error"]) &
                     ((Candidate.processing_version < 8) |
                      ((Candidate.status == "error") & retry_due) |
                      (((Candidate.analysis_mode == "deterministic") | retry_due) if llm_ready else False))),
                ))
                if review_only:
                    review_due = (Candidate.processing_version < 8)
                    if llm_ready:
                        review_due = review_due | ((Candidate.reason == "llm_unavailable") &
                                                   ((Candidate.analysis_mode == "deterministic") | retry_due))
                    query = select(Candidate).where(
                        Candidate.status.in_(["pending", "review_required"]), review_due)
                if only_urls:
                    query = select(Candidate)
                from .publication_retry import eligible
                from .llm_retry import eligible as llm_retry_eligible
                query = query.where(*eligible(), *llm_retry_eligible())
                if only_source:
                    query = query.where(Candidate.source_id == only_source)
                if archive_window and not only_urls:
                    query = query.where(Candidate.archive_scope[0].as_string() == scope[0])
                if only_urls:
                    query = query.where(Candidate.url.in_([canonical_url(url) for url in only_urls]))
                source_weight = case(
                    (RegistrySource.id == "show-hn-rss", 5),
                    (RegistrySource.source_type == "startup_platform", 5),
                    (RegistrySource.source_type.in_(["university", "hackathon", "accelerator", "event"]), 4),
                    (RegistrySource.source_type == "community", 3),
                    else_=1,
                )
                archive_hint = case(
                    (Candidate.article["_feed_date"].as_string().like(f"{scope[0][:4]}%"), 1),
                    (Candidate.url.contains(f"/{scope[0][:4]}/"), 1),
                    else_=0,
                ) if scope else None
                if process and only_urls:
                    rows = list(session.scalars(query.limit(self.settings.max_candidates)))
                elif process:
                    # One candidate per source each round prevents a large Global archive
                    # from starving smaller Uzbekistan feeds during hourly processing.
                    ranked = select(
                        Candidate.url.label("url"),
                        func.row_number().over(partition_by=Candidate.source_id,
                                               order_by=((archive_hint.desc(), Candidate.updated_at, Candidate.url)
                                                         if archive_hint is not None else
                                                         (Candidate.updated_at, Candidate.url))).label("source_position"),
                        source_weight.label("source_weight"),
                        RegistrySource.priority.label("source_priority"),
                        case((RegistrySource.country == "Uzbekistan", 1), else_=0).label("local_source"),
                        (archive_hint if archive_hint is not None else literal(0)).label("archive_hint"),
                    ).outerjoin(RegistrySource, Candidate.source_id == RegistrySource.id).where(query.whereclause).subquery()
                    urls = session.scalars(select(ranked.c.url).order_by(
                        ranked.c.archive_hint.desc(),
                        ranked.c.local_source.desc(),
                        ranked.c.source_position,
                        ranked.c.source_weight.desc(), ranked.c.source_priority.desc(), ranked.c.url,
                    ).limit(self.settings.max_candidates)).all()
                    by_url = {row.url: row for row in session.scalars(
                        select(Candidate).where(Candidate.url.in_(urls))).all()} if urls else {}
                    rows = [by_url[url] for url in urls]
                else:
                    rows = []
                work = [(row.url, row.article or {}, row.source_id) for row in rows]
                if process and not work:
                    stop_reason = "queue_empty"
            for url, cached, source_id in work:
                if (self.llm_service and self.llm_service.available and
                        not getattr(self.llm_service, "operational", True)):
                    counts["provider_circuit_open"] += 1
                    errors.append({"source": "llm", "stage": "classification",
                                   "code": "provider_circuit_open"})
                    stop_reason = "ai_provider_limit"
                    break
                raw_id = None
                self.last_llm_analysis = None
                counts["candidates"] += 1
                source_bucket = yield_by_source[source_id or "unknown"]
                source_bucket["processed"] += 1
                try:
                    with self.factory.begin() as session:
                        adapter = source_id or "event_discovery"
                        raw = session.get(RawDiscovery, cached.get("_raw_id")) if cached.get("_raw_id") else None
                        raw = raw or session.scalar(select(RawDiscovery).where(
                            RawDiscovery.source_adapter == adapter, RawDiscovery.source_url == url))
                        if raw is None:
                            raw, _ = ingest_raw(session, source_adapter=adapter, source_url=url,
                                                source_name=adapter, title=cached.get("title", ""),
                                                source_type="legacy_candidate", raw_payload={"candidate_url": url})
                            counts["raw_discoveries"] += 1
                        action, reason, known_project_id = (("classify", "", None)
                            if cached.get("_deferred_catalog_entries") or cached.get("_validated_catalog_result") else cheap_decision(session, raw))
                        raw_id = raw.id
                        from .network import unsuitable_url
                        unsuitable = unsuitable_url(cached.get("_fetch_url", url))
                        if action == "classify" and unsuitable:
                            action, reason = "reject", unsuitable
                        if action != "classify":
                            record_transition(raw, "rejected" if action == "reject" else "processed", reason,
                                              known_project_id, now)
                            candidate = session.get(Candidate, url)
                            candidate.status = "rejected" if action == "reject" else "published"
                            candidate.reason = reason
                            candidate.processing_version = 8
                            candidate.updated_at = now
                            if known_project_id:
                                candidate.project_ids = list(dict.fromkeys([*(candidate.project_ids or []), known_project_id]))
                                if candidate.entity_type != "PROJECT":
                                    candidate.classification_history = history(candidate.classification_history,
                                        candidate.entity_type, "legacy", "superseded_entity_type", now)
                                    candidate.entity_type = "PROJECT"
                        else:
                            raw.status = "processing"
                            raw.processing_started_at = now
                    if action != "classify":
                        bucket = "pre_filtered" if action == "reject" else "duplicates"
                        counts[bucket] += 1
                        source_bucket[bucket] += 1
                        continue
                    if not cached.get("_queued") and cached.get("text"):
                        article = Article.model_validate(cached)
                        from .telemetry import record
                        record("extraction", method="cached_source", words=len(article.text.split()))
                    else:
                        with self.factory() as session:
                            stored_raw = session.get(RawDiscovery, raw_id)
                            telegram = stored_raw.source_type == "telegram"
                            raw_data = (stored_raw.source_name, stored_raw.title, stored_raw.raw_text,
                                        stored_raw.publication_date, stored_raw.page_type,
                                        stored_raw.source_adapter) if telegram else None
                        if raw_data:
                            article = Article(url=url, publisher=raw_data[0], title=raw_data[1],
                                              text=raw_data[2] or "", published_at=raw_data[3],
                                              kind="unknown", page_type=raw_data[4], adapter=raw_data[5])
                        else:
                            article = self.discovery.article(cached.get("_fetch_url", url), parse_date(cached.get("_feed_date")))
                    article.discovery_url = article.discovery_url or cached.get("_discovery_url")
                    article.discovery_title = article.discovery_title or cached.get("_discovery_title", "")
                    article.source_id = source_id or article.source_id
                    with self.factory.begin() as session:
                        raw = session.get(RawDiscovery, raw_id)
                        raw.title = article.title
                        raw.description = article.text[:500]
                        raw.raw_text = article.text
                        raw.publication_date = article.published_at
                        raw.page_type = article.page_type or raw.page_type
                        raw.raw_payload = {**(raw.raw_payload or {}), "publisher": article.publisher,
                                           "language": article.language, "discovery_url": article.discovery_url}
                    window = getattr(self.discovery, "window", None)
                    if window and article.published_at and not window[0] <= aware(article.published_at).astimezone(TASHKENT).date() <= window[1]:
                        result = CatalogResult("NOT_PROJECT", 0.95, reason="outside_archive_window",
                                               analysis_method="deterministic")
                    else:
                        if cached.get("_validated_catalog_result"):
                            from .catalog import parse_classifier_response
                            saved = cached["_validated_catalog_result"]
                            result = parse_classifier_response(saved, article.title + "\n" + article.text)
                            from .telemetry import record
                            record("continuation", outcome="validated_result_reused", provider=saved.get("provider"))
                        elif cached.get("_deferred_catalog_entries"):
                            entries = tuple(CatalogEntry.model_validate(item) for item in cached["_deferred_catalog_entries"])
                            result = CatalogResult("MULTI", min(item.confidence for item in entries), entries,
                                                   analysis_method=cached.get("_deferred_analysis_method", "llm"))
                        else:
                            result = self._classify(article)
                    if self.last_llm_analysis:
                        # No deadline checks before this checkpoint: a validated response
                        # must survive expiry during post-HTTP accounting or publication.
                        from .telemetry import db_work
                        with db_work("validated_checkpoint"):
                            with self.factory.begin() as session:
                                stored = session.get(Candidate, url)
                                stored.article = {**article.model_dump(mode="json"), "_validated_catalog_result": {
                                    "classification": result.classification, "confidence": result.confidence,
                                    "entries": [entry.model_dump(mode="json") for entry in result.entries],
                                    **(result.entries[0].model_dump(mode="json") if result.classification == "PROJECT" and result.entries else {}),
                                    "reason": result.reason, "provider": self.last_llm_analysis.provider,
                                    "model": self.last_llm_analysis.model, "prompt_version": self.last_llm_analysis.prompt_version,
                                    "attempt_count": self.last_llm_analysis.attempt_count}}
                                stored.status, stored.reason = "queued", "validated_result_pending_commit"
                    if result.entries:
                        counts["project_candidates"] += len(result.entries)
                        source_bucket["project_candidates"] += len(result.entries)
                    from .telemetry import finishing_decision
                    with finishing_decision():
                        with self.factory.begin() as session, session.no_autoflush:
                            candidate = session.get(Candidate, url)
                            candidate.article = {**article.model_dump(mode="json"),
                                                 "_catalog_entries": [entry.model_dump(mode="json") for entry in result.entries]}
                            candidate.attempts += 1
                            candidate.updated_at = now
                            candidate.last_run_id = run_id
                            candidate.processing_version = 8
                            candidate.analysis_mode = result.analysis_method
                            outcomes = save_catalog_result(session, article, result, now, self.settings)
                            if candidate.reason == "llm_unavailable" and result.analysis_method == "llm_failed":
                                from .llm_retry import unavailable
                                unavailable(candidate, cached, now)
                                candidate.status_history = history(candidate.status_history, "REVIEW_REQUIRED", "retry_policy", candidate.reason, now)
                            raw = session.get(RawDiscovery, raw_id)
                            record_transition(raw, "processed" if candidate.status == "published" else
                                              "rejected" if candidate.status == "rejected" else "review_required",
                                              candidate.reason, (candidate.project_ids or [None])[0], now)
                            raw.candidate_url = url
                            raw.raw_payload = {**(raw.raw_payload or {}), "project_ids": candidate.project_ids or []}
                            if self.last_llm_analysis:
                                raw.llm_provider = self.last_llm_analysis.provider
                                raw.llm_model = self.last_llm_analysis.model
                                raw.llm_attempt_count += self.last_llm_analysis.attempt_count
                                raw.classifier_prompt_version = self.last_llm_analysis.prompt_version
                                raw.analyzed_at = now
                            elif cached.get("_validated_catalog_result"):
                                saved = cached["_validated_catalog_result"]
                                raw.llm_provider, raw.llm_model = saved.get("provider", ""), saved.get("model", "")
                                raw.classifier_prompt_version = saved.get("prompt_version", PROMPT_VERSION)
                                raw.llm_attempt_count = max(raw.llm_attempt_count, saved.get("attempt_count", 0))
                                raw.analyzed_at = now
                            elif self.llm_service and self.llm_service.last_attempt_count:
                                raw.llm_attempt_count += self.llm_service.last_attempt_count
                                raw.classifier_prompt_version = PROMPT_VERSION
                                raw.analyzed_at = now
                    if outcomes.get("auto_published"):
                        from .free_budget import current_budget
                        budget = current_budget()
                        if budget:
                            budget._checked_at = -100.0  # Publication changes the target guard.
                    for key, value in outcomes.items():
                        counts[key] += value
                        source_bucket[key] += value
                    with self.factory() as session:
                        daily = today_stats(session, self.settings)
                    if daily["published"] >= daily["limit"]:
                        stop_reason = "daily_publish_limit_reached"
                        break
                    if self.last_llm_analysis and self.settings.llm_batch_delay_seconds:
                        from .free_budget import current_budget
                        if not current_budget():
                            sleep(self.settings.llm_batch_delay_seconds)
                        # Bounded daily jobs already enforce provider spacing;
                        # an extra post-analysis delay does not improve limits.
                except DailyLimitReached as exc:
                    stop_reason = exc.reason
                    break
                except FetchError as exc:
                    with self.factory.begin() as session:
                        candidate = session.get(Candidate, url)
                        candidate.status, candidate.reason = ("pending" if isinstance(exc, CandidateTimeout) else "error"), str(exc)
                        candidate.last_run_id = run_id
                        candidate.attempts += 1
                        candidate.processing_version = 8
                        candidate.updated_at = now
                        if raw_id is not None:
                            record_transition(session.get(RawDiscovery, raw_id), "failed", str(exc), when=now)
                    errors.append({"source": url, "stage": "processing" if isinstance(exc, CandidateTimeout) else "fetch", "code": str(exc)})
                    source_bucket["errors"] += 1
                except (ClassifierFailure, ValueError) as exc:
                    reason = str(exc)
                    with self.factory.begin() as session:
                        candidate = session.get(Candidate, url)
                        candidate.status, candidate.reason = "review_required", reason
                        candidate.analysis_mode = "llm" if self.settings.ai_key else "deterministic"
                        candidate.processing_version = 8
                        candidate.attempts += 1
                        candidate.updated_at = now
                        if raw_id is not None:
                            record_transition(session.get(RawDiscovery, raw_id), "review_required", reason, when=now)
                    counts["review_required"] += 1
                    source_bucket["review_required"] += 1
            if reanalyze and stop_reason != "daily_publish_limit_reached":
                self._enrich(now, counts, errors)
            if not stop_reason:
                stop_reason = "source_error" if source_errors else "batch_budget_reached" if work else "queue_empty"
            status = "partial" if errors else "completed"
        except BudgetStop as exc:
            status, stop_reason = "stopped", str(exc)
        except Exception as exc:
            status = "failed"
            from .publication_retry import record_failure
            from .safe_errors import safe_error
            if locals().get("url"):
                try:
                    record_failure(self.factory, url, exc, run_id)
                except Exception as retry_error:
                    # Keep the original publication failure and still release leases.
                    errors.append({"stage": "publication_retry_bookkeeping",
                                   **safe_error(retry_error, function="publication_retry.record_failure", candidate_url=url)})
            errors.append({"source": "pipeline", "stage": "catalog",
                           **safe_error(exc, function="catalog_pipeline.run", candidate_url=locals().get("url"))})
            raise
        finally:
            try:
                if run_id is not None:
                    with self.factory.begin() as session:
                        run = session.get(Run, run_id)
                        run.finished_at, run.status = now_utc(), status
                        run.counts = dict(counts)
                        run.errors = errors[:100]
                        run.details = {"mode": "catalog_archive" if archive else "catalog_fresh",
                                       "last_error": errors[-1] if errors else None,
                                       "window": [part.isoformat() for part in self.discovery.window] if getattr(self.discovery, "window", None) else [],
                                       "coverage": getattr(self.discovery, "archive_coverage", []),
                                       "limits": {"max_candidates": self.settings.max_candidates,
                                                  "archive_pages": self.settings.archive_pages},
                                       "source_yield": {key: dict(value) for key, value in yield_by_source.items()},
                                       "stop_reason": stop_reason,
                                       "processed": counts["candidates"],
                                       "published": counts["auto_published"],
                                       "daily_publication": today_stats(session, self.settings),
                                       "llm_providers": self.llm_service.status() if self.llm_service else [],
                                       "diagnostics": self._diagnostics(),
                                       "remaining_queue": session.scalar(select(func.count()).select_from(Candidate).where(Candidate.status.in_(["queued", "pending", "review_required"])))}
                        report_details = run.details
                        run.duration_seconds = round(monotonic() - began, 2)
            finally:
                self.release_owner(owner)
        return {"id": run_id, "status": status, "counts": dict(counts), "errors": errors[:100],
                "details": report_details}
