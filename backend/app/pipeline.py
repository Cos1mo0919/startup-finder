import logging
from datetime import timedelta
from time import monotonic
from uuid import uuid4
from sqlalchemy import and_, or_, select, update
from .analysis import AnalysisError, analyzer_for, validate_analysis
from .collectors.sources import Discovery
from .collectors.parsers import PARSER_VERSION
from .collectors.archive import url_day
from .dates import valid_date, parse_date
from .db import (
    Candidate,
    EcosystemSignal,
    Lease,
    Project,
    RegistrySource,
    RejectedCandidate,
    Run,
    Source,
    now_utc,
)
from .dedup import find_duplicate, fingerprint
from .detection import material_type, normalize, project_detector
from .network import FetchError, WebClient, canonical_url
from .ranking import score
from .evidence import attach_evidence, audit_existing, evaluate_project, record_rejection
from .events import save_event
from .registry import seed_registry
from .sectors import classify_sectors
from .schemas import Analysis, Article
from .intelligence import MINOR, cited_problem_scores, entity_type, meaningful_problem, problem_from_article, problems_from_article, problem_gate, upsert_problem, opportunity
from .publication import refresh_publication
from .signal_quality import signal_status

logger = logging.getLogger(__name__)


def archive_priority(candidate, window):
    """Spend a bounded yearly run on likely in-window URLs first; hints never validate dates."""
    cached = candidate.article or {}
    feed_date = parse_date(cached.get("_feed_date")) if cached.get("_feed_date") else None
    hinted_day = url_day(candidate.url) or (feed_date.date() if feed_date else None)
    date_rank = 0 if hinted_day and window[0] <= hinted_day <= window[1] else 2 if hinted_day else 1
    title = (cached.get("title") or "").casefold()
    project_terms = (
        "loyiha", "startap", "startup", "ilova", "platforma", "prototip",
        "hackathon", "hakaton", "demo day", "project", "prototype",
        "разработ", "стартап", "приложен", "проект",
    )
    title_rank = 0 if any(term in title for term in project_terms) else 1
    return date_rank, title_rank


class Pipeline:
    def __init__(self, settings, factory, discovery=None, analyzer=None):
        self.settings, self.factory = settings, factory
        self.web = None if discovery else WebClient(settings)
        self.discovery = discovery or Discovery(settings, self.web, factory=factory)
        self.analyzer = analyzer or analyzer_for(settings)
        seed_registry(factory, settings.sources_file)
        self.last_persist_visible = False
        self.pre_run_hidden = set()

    def close(self):
        if self.web:
            self.web.close()

    def acquire(self, owner, now):
        from .writer import current_writer, renew_writer
        if current_writer(self.factory):
            renew_writer(self.factory)
            return True
        with self.factory.begin() as session:
            result = session.execute(
                update(Lease)
                .where(Lease.name == "pipeline", Lease.expires_at <= now)
                .values(owner=owner, expires_at=now + timedelta(minutes=20))
            )
            if result.rowcount:
                for run in session.scalars(select(Run).where(Run.status == "running")):
                    run.status = "interrupted"
                    run.finished_at = now
                    run.errors = [{"source": "Tizim", "code": "previous_run_interrupted"}]
            return result.rowcount == 1

    def heartbeat(self, owner):
        from .writer import current_writer, renew_writer
        if current_writer(self.factory):
            renew_writer(self.factory)
            return
        now = now_utc()
        with self.factory.begin() as session:
            result = session.execute(
                update(Lease)
                .where(Lease.name == "pipeline", Lease.owner == owner, Lease.expires_at > now)
                .values(expires_at=now + timedelta(minutes=20))
            )
            if result.rowcount != 1:
                raise RuntimeError("pipeline_lease_lost")

    def release(self, session, owner):
        from .writer import current_writer
        if not current_writer(self.factory):
            session.execute(update(Lease).where(Lease.name == "pipeline", Lease.owner == owner)
                            .values(expires_at=now_utc(), owner=""))

    def persist(self, analysis, articles, now, allow_shared_source=False, official_evidence=None):
        validate_analysis(analysis, articles)
        # Retain only sources actually cited by validated facts.
        cited = {canonical_url(f.source_url) for f in analysis.facts}
        articles = [a for a in articles if canonical_url(a.url) in cited]
        with self.factory.begin() as session:
            project = find_duplicate(session, analysis, [a.url for a in articles], allow_shared_source)
            if project and project.publication_method == "admin" and project.publication_status != "PUBLISHED":
                self.last_persist_visible = False
                return project.id
            created = project is None
            previously_visible = bool(project and project.publication_status == "PUBLISHED")
            if project is None:
                project = Project(
                    name=analysis.name,
                    normalized_project_name=normalize(analysis.name),
                    creator=analysis.creator,
                    organization=analysis.organization,
                    city=analysis.city,
                    event=analysis.event,
                    country=analysis.country,
                    main_url=canonical_url(analysis.main_url) if analysis.main_url else None,
                    discovery_source_url=articles[0].discovery_url,
                    fingerprint=fingerprint(analysis),
                    aliases=analysis.aliases,
                    first_seen=now,
                    last_seen=now,
                    published_at=min(a.published_at for a in articles),
                    category=analysis.category,
                    audience=analysis.audience,
                    content=analysis.model_dump(mode="json"),
                    images=[],
                    event_id=articles[0].event_id,
                )
                session.add(project)
                session.flush()
            else:
                # Preserve first_seen and prior facts; improve keyless analysis when real AI becomes available.
                previous = Analysis.model_validate(project.content)
                selected = (
                    analysis
                    if previous.analysis_mode == "extractive"
                    and (
                        analysis.analysis_mode == "ai"
                        or (not previous.creator and analysis.creator)
                        or analysis.extraction_version > previous.extraction_version
                    )
                    else previous
                )
                facts = list(selected.facts)
                keys = {(f.source_url, f.quote) for f in facts}
                for fact in [*previous.facts, *analysis.facts]:
                    if (fact.source_url, fact.quote) not in keys and len(facts) < 20:
                        facts.append(fact)
                        keys.add((fact.source_url, fact.quote))
                selected.facts = facts
                project.content = selected.model_dump(mode="json")
                if selected is analysis:
                    project.name = selected.name
                    project.normalized_project_name = normalize(selected.name)
                project.aliases = list(dict.fromkeys([*project.aliases, *analysis.aliases, analysis.name]))[
                    :20
                ]
                project.last_seen = now
                project.category, project.audience = selected.category, selected.audience
                for field in ("creator", "organization", "city", "event"):
                    if not getattr(project, field) and getattr(selected, field):
                        setattr(project, field, getattr(selected, field))
                if not project.main_url and selected.main_url:
                    project.main_url = canonical_url(selected.main_url)
                if not project.discovery_source_url and articles[0].discovery_url:
                    project.discovery_source_url = articles[0].discovery_url
            if articles[0].event_id and (
                not project.event_id
                or (
                    len(project.sources) == 1
                    and project.sources[0].url == canonical_url(articles[0].url)
                    and project.event_id != articles[0].event_id
                )
            ):
                # Repair a stale follow-up association when the project's only
                # source is itself a report about a different, named event.
                project.event_id = articles[0].event_id
            known = {s.url for s in project.sources}
            for article in articles:
                url = canonical_url(article.url)
                if url not in known:
                    project.sources.append(
                        Source(
                            url=url,
                            source_id=article.source_id if article.source_id and session.get(RegistrySource, article.source_id) else None,
                            publisher=article.publisher,
                            kind=article.kind,
                            published_at=article.published_at,
                            retrieved_at=now,
                            quotes=[f.quote for f in analysis.facts if canonical_url(f.source_url) == url],
                        )
                    )
                    known.add(url)
                if article.image_url and not any(i["url"] == article.image_url for i in project.images):
                    project.images = [
                        *project.images,
                        {"url": article.image_url, "source_url": article.url, "publisher": article.publisher},
                    ][:5]
            stored = Analysis.model_validate(project.content)
            project.rating, project.rating_components = score(stored, project.sources)
            project.primary_sector, project.sectors = classify_sectors(stored)
            attach_evidence(session, project, analysis, articles, now)
            if official_evidence:
                from .db import ProjectEvidence

                official_url, official_quote = official_evidence
                existing_official = session.scalar(select(ProjectEvidence).where(
                    ProjectEvidence.project_id == project.id,
                    ProjectEvidence.url == official_url,
                    ProjectEvidence.evidence_type == "official_website",
                    ProjectEvidence.quote == official_quote,
                ))
                if existing_official is None:
                    project.evidence_records.append(ProjectEvidence(
                        project_id=project.id, url=official_url,
                        evidence_type="official_website", quote=official_quote,
                        confidence=0.6,
                        notes="Article project link and linked page name match",
                    ))
            reasons = evaluate_project(session, project, self.settings.evidence_min_score)
            gate, gate_reason, finding = problem_gate(stored, articles)
            project.problem_gate_status, project.problem_gate_reason = gate, gate_reason
            if finding:
                findings = [item for article in articles for item in problems_from_article(article, stored)]
                # Prefer a directly named problem with concrete cost or consequence.
                findings.sort(key=lambda item: (
                    bool(normalize(stored.name) in normalize(item["quote"])),
                    bool(cited_problem_scores(item).get("current_cost")),
                    bool(cited_problem_scores(item).get("pain_strength")),
                ), reverse=True)
                finding = findings[0] if findings else finding
                project.problem_statement = finding["statement"]
                project.problem_subject = finding["subject"]
                project.problem_scope = finding["scope"]
                project.problem_evidence_summary = finding["quote"]
                upsert_problem(session, finding, project.primary_sector, project.country, project)
                secondaries = []
                for item in findings[1:4]:
                    if normalize(item["statement"]) == normalize(finding["statement"]):
                        continue
                    linked = upsert_problem(session, item, project.primary_sector, project.country, project)
                    secondaries.append({"problem_id": linked.id, "statement": item["statement"], "source_url": item["source_url"]})
                project.secondary_problems = secondaries
            assessment = opportunity(cited_problem_scores(finding) if finding else {}, 2, gate, [r for r in reasons if r in ("creator_unknown", "existence_unconfirmed", "missing_source")])
            project.opportunity_details = assessment
            project.opportunity_score = assessment["score"]
            project.opportunity_grade = assessment["grade"]
            refresh_publication(project)
            self.last_project_status = project.publication_status
            self.last_project_reason = project.publication_reason
            self.last_persist_visible = project.publication_status == "PUBLISHED"
            self.last_newly_published = bool(
                self.last_persist_visible and (not previously_visible or project.id in self.pre_run_hidden)
            )
            if self.last_newly_published:
                self.pre_run_hidden.discard(project.id)
            self.last_project_id = project.id
            if reasons:
                record_rejection(
                    session,
                    articles[0].url,
                    project.name,
                    reasons,
                    project.confidence,
                    project.detection_signals,
                )
            else:
                from .db import RejectedCandidate

                for source in project.sources:
                    rejected = session.get(RejectedCandidate, source.url)
                    if rejected:
                        session.delete(rejected)
            return created

    def run(self, archive=False, window=None, discover=True, only_urls=None):
        from collections import Counter
        from datetime import date
        from .queries import in_window
        from .detection import early_reason
        from .diagnostics import summarize_run

        archive = archive or window is not None
        owner, start, began = str(uuid4()), now_utc(), monotonic()
        if not self.acquire(owner, start):
            return {"status": "busy"}
        counts = dict(
            sources_checked=0,
            candidates_found=0,
            candidates=0,
            rejected=0,
            duplicates=0,
            new_projects=0,
            pending=0,
            stop_filtered=0,
            ecosystem_signals=0,
            problems=0,
            events=0,
            event_projects=0,
            university_projects=0,
            processed_ai=0,
            processed_fallback=0,
            ai_errors=0,
            translation_errors=0,
        )
        errors, reasons, origins = [], Counter(), {}
        details = {
            "mode": "archive" if archive else "fresh",
            "discovery_mode": "queue_only"
            if not discover
            else "year_backfill"
            if window
            else "current_listings",
            "limits": {
                "archive_pages": self.settings.archive_pages,
                "max_candidates": self.settings.max_candidates,
            },
            "window": [d.isoformat() for d in window] if window else [],
            "coverage": [],
        }
        with self.factory.begin() as session:
            run = Run(started_at=start, counts=counts.copy(), details=details)
            session.add(run)
            session.flush()
            run_id = run.id
        status = "failed"
        try:
            with self.factory() as session:
                self.pre_run_hidden = set(session.scalars(select(Project.id).where(Project.publication_status != "PUBLISHED")))
            audit_existing(self.factory, self.settings.evidence_min_score)
            if hasattr(self.discovery, "window"):
                self.discovery.window = window
            links, discovery_errors, checked = (
                self.discovery.discover(start, archive) if discover else ([], [], 0)
            )
            errors.extend(discovery_errors)
            if discover and hasattr(self.discovery, "follow_events"):
                event_links, event_errors = self.discovery.follow_events(start)
                links = event_links + links
                errors.extend(event_errors)
            counts["sources_checked"] = checked
            counts["candidates_found"] = len({canonical_url(i["url"]) for i in links})
            details["coverage"] = getattr(self.discovery, "archive_coverage", [])
            # Store every discovered URL before applying processing limits. No silent truncation.
            with self.factory.begin() as session:
                for item in links:
                    url = canonical_url(item["url"])
                    row = session.get(Candidate, url)
                    if row is None:
                        row = Candidate(
                            url=url,
                            article={
                                "_queued": True,
                                "_fetch_url": item["url"],
                                "title": item.get("title", ""),
                                "_discovery_url": item.get("discovery_url"),
                                "_feed_date": item["published_at"].isoformat()
                                if item.get("published_at")
                                else None,
                            },
                            status="queued",
                            source_id=item.get("source_id"),
                            event_id=item.get("event_id"),
                            origin=item.get("origin", "other"),
                            archive_scope=[d.isoformat() for d in window] if window else [],
                        )
                        session.add(row)
                        session.flush()
                    elif window and row.reason in ("outside_archive_window", "old_date", "date_out_of_range"):
                        row.archive_scope = [d.isoformat() for d in window]
                    elif window and row.status == "queued":
                        # A current listing may first expose this URL in an older yearly run.
                        # Route an unprocessed dated URL when it is rediscovered in its own year.
                        # The fetched publication date is still checked against the window below.
                        day = url_day(url)
                        if day and window[0] <= day <= window[1]:
                            row.archive_scope = [d.isoformat() for d in window]
                    if item.get("event_id") and not row.event_id:
                        row.event_id = item["event_id"]
                        row.origin = "event_discovery"
                    elif not row.event_id and item.get("origin"):
                        row.origin = item["origin"]
                reanalysis = set()
                if self.settings.ai_key:
                    reanalysis = set(
                        session.scalars(
                            select(Source.url)
                            .join(Project)
                            .where(Project.content["analysis_mode"].as_string() == "extractive")
                        )
                    )
                candidates = list(
                    session.scalars(
                        select(Candidate)
                        .where(
                            or_(
                                Candidate.status.in_(["queued", "pending", "error"]),
                                and_(
                                    Candidate.processing_version < 5,
                                    Candidate.status.in_(["rejected", "event", "published"]),
                                ),
                                Candidate.url.in_(reanalysis),
                                Candidate.url.in_(only_urls) if only_urls else False,
                                and_(
                                    Candidate.reason.in_(
                                        ["date_out_of_range", "outside_archive_window", "old_date"]
                                    ),
                                    Candidate.status == "rejected",
                                )
                                if archive
                                else False,
                            )
                        )
                        .order_by(Candidate.updated_at, Candidate.url)
                    )
                )
                if only_urls:
                    candidates = [c for c in candidates if c.url in only_urls]
                allowed_source_ids = getattr(self.discovery, "allowed_source_ids", None)
                if allowed_source_ids is not None:
                    candidates = [c for c in candidates if c.source_id in allowed_source_ids]
            if window:
                candidates = [
                    c
                    for c in candidates
                    if not c.archive_scope or c.archive_scope == [d.isoformat() for d in window]
                ]
                candidates.sort(key=lambda c: archive_priority(c, window))
            for candidate in candidates[: self.settings.max_candidates * 2]:
                self.heartbeat(owner)
                url, article, stage = candidate.url, None, "parser"
                origin = candidate.origin or "other"
                bucket = origins.setdefault(origin, Counter())
                bucket["candidates"] += 1
                counts["candidates"] += 1
                with self.factory.begin() as session:
                    row = session.get(Candidate, url)
                    row.last_run_id, row.processing_version = run_id, 6
                    row.attempts += 1
                try:
                    cached = candidate.article
                    if not cached.get("_queued") and cached.get("parser_version", 1) == PARSER_VERSION:
                        article = Article.model_validate(cached)
                    else:
                        article = self.discovery.article(
                            cached.get("_fetch_url", url), parse_date(cached.get("_feed_date"))
                        )
                    article.source_id = candidate.source_id or article.source_id
                    article.event_id = candidate.event_id or article.event_id
                    article.discovery_url = (cached or {}).get("_discovery_url") or article.discovery_url
                    article.discovery_title = (cached or {}).get("title", "") or article.discovery_title
                    with self.factory.begin() as session:
                        row = session.get(Candidate, url)
                        row.article = article.model_dump(mode="json")
                        row.source_id = article.source_id
                    scope = window or (
                        tuple(date.fromisoformat(x) for x in candidate.archive_scope)
                        if candidate.archive_scope
                        else None
                    )
                    reason = ""
                    if article.published_at is None:
                        reason = "unknown_publication_date"
                    elif not valid_date(article.published_at, start, archive=True):
                        reason = "invalid_date"
                    elif scope and not in_window(article.published_at, scope):
                        reason = "outside_archive_window"
                    elif not archive and not scope and not valid_date(article.published_at, start):
                        reason = "old_date"
                    if reason:
                        self.mark(url, "rejected", reason)
                        reasons[reason] += 1
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                        bucket["rejected"] += 1
                        continue
                    stage = "classification"
                    classification = material_type(article)
                    public_type = entity_type(article)
                    detector, detector_reason = project_detector(article)
                    if detector == "SIGNAL_ONLY":
                        public_type = "SIGNAL"
                    elif detector == "NON_PROJECT":
                        public_type = "IGNORE"
                    elif detector == "PROJECT_CANDIDATE":
                        public_type = "PROJECT"
                    with self.factory.begin() as session:
                        row = session.get(Candidate, url)
                        row.entity_type = public_type
                        row.detector_result = detector
                    event_id, event_created = (
                        save_event(self.factory, article, start)
                        if classification in ("PROJECT", "EVENT")
                        else (None, False)
                    )
                    counts["events"] += int(event_created)
                    if event_id and classification == "PROJECT":
                        # An event identified on this page is stronger context
                        # than a follow-up queue's inherited event ID.
                        article.event_id = event_id
                    if public_type == "SIGNAL":
                        with self.factory.begin() as session:
                            if session.get(EcosystemSignal, url) is None:
                                is_hn = article.url.startswith("https://news.ycombinator.com/item?")
                                source = session.get(RegistrySource, article.source_id) if article.source_id else None
                                session.add(
                                    EcosystemSignal(
                                        url=url,
                                        title=article.title,
                                        source_id=article.source_id,
                                        signal_type="TECHNOLOGY" if is_hn else "REGULATION" if classification != "ECOSYSTEM_SIGNAL" else "PROGRAM",
                                        published_at=article.published_at,
                                        quote=article.text[:1500],
                                        summary_uz=("Show HN hamjamiyatida taqdim etilgan material: " + article.title.split(" | ")[0])[:800] if is_hn else article.title,
                                        country=source.country if source and source.country else "Uzbekistan",
                                        region=source.region if source else "Uzbekistan",
                                        confidence=0.3 if is_hn else 0.5,
                                        intelligence_status=signal_status(article.title, article.text),
                                        discovered_at=start,
                                    )
                                )
                        self.mark(url, "ecosystem", "")
                        counts["ecosystem_signals"] += 1
                        bucket["ecosystem"] += 1
                        continue
                    if public_type == "PROBLEM" and meaningful_problem(article):
                        finding = problem_from_article(article)
                        if finding:
                            with self.factory.begin() as session:
                                upsert_problem(session, finding)
                            self.mark(url, "problem", "")
                            counts["problems"] += 1
                            bucket["problems"] += 1
                            continue
                    if classification == "EVENT":
                        self.mark(url, "event", "")
                        bucket["events"] += 1
                        continue
                    if public_type != "PROJECT":
                        reason = "minor_feature" if MINOR.search(article.title + " " + article.text[:2000]) else detector_reason or early_reason(article) or "not_project"
                        self.mark(url, "rejected", reason)
                        reasons[reason] += 1
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                        bucket["rejected"] += 1
                        continue
                    stage = "ai" if self.settings.ai_key else "fallback"
                    analysis = self.analyzer.analyze([article])
                    if analysis is None:
                        from .fallback import pending_reason

                        self.mark(url, "pending", pending_reason(article))
                        counts["pending"] += 1
                        bucket["pending"] += 1
                        continue
                    articles = [article]
                    # Corroboration failures are scoped to this stage, never discard the first source.
                    try:
                        for extra_url in self.discovery.corroborate(analysis.name, article.url, analysis.country):
                            try:
                                extra = self.discovery.article(extra_url)
                                if valid_date(extra.published_at, start, archive=True) and normalize(
                                    analysis.name
                                ) in normalize(extra.title + " " + extra.text):
                                    articles.append(extra)
                            except FetchError as exc:
                                errors.append(
                                    {"source": extra_url, "stage": "corroboration", "code": str(exc)}
                                )
                        if len(articles) > 1:
                            combined = self.analyzer.analyze(articles)
                            if combined and normalize(combined.name) == normalize(analysis.name):
                                analysis = combined
                    except (FetchError, AnalysisError) as exc:
                        errors.append({"source": url, "stage": "corroboration", "code": str(exc)})
                    official_evidence = None
                    if not analysis.main_url and hasattr(self.discovery, "resolve_official"):
                        try:
                            official_evidence = self.discovery.resolve_official(analysis.name, article)
                            if official_evidence:
                                official_url, _ = official_evidence
                                analysis.main_url = official_url
                                analysis.links["official"] = official_url
                        except FetchError as exc:
                            errors.append({"source": url, "stage": "official_resolution", "code": str(exc)})
                    stage = "validation"
                    self.persist(
                        analysis, articles, start, allow_shared_source=bool(article.event_id),
                        official_evidence=official_evidence,
                    )
                    primary_project_id = self.last_project_id
                    mode = "processed_ai" if analysis.analysis_mode == "ai" else "processed_fallback"
                    counts[mode] += 1
                    bucket[mode] += 1
                    with self.factory.begin() as session:
                        candidate_row = session.get(Candidate, url)
                        candidate_row.analysis_mode = analysis.analysis_mode
                        candidate_row.project_ids = list(dict.fromkeys([*(candidate_row.project_ids or []), primary_project_id]))
                    if self.last_persist_visible:
                        label = "new_projects" if self.last_newly_published else "duplicates"
                        counts[label] += 1
                        bucket[label] += 1
                        counts["event_projects"] += int(self.last_newly_published and bool(article.event_id))
                        counts["university_projects"] += int(
                            self.last_newly_published and (origin == "university" or article.kind == "university")
                        )
                        if self.last_newly_published and article.source_id:
                            with self.factory.begin() as session:
                                source = session.get(RegistrySource, article.source_id)
                                if source:
                                    source.new_projects += 1
                        self.mark(url, "published", "")
                    elif self.last_project_status == "REVIEW_REQUIRED":
                        counts["pending"] += 1
                        bucket["pending"] += 1
                        self.mark(url, "review_required", self.last_project_reason)
                    else:
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                        bucket["rejected"] += 1
                        with self.factory() as session:
                            rejection = session.get(RejectedCandidate, canonical_url(article.url))
                            for reason in rejection.reasons if rejection else ["insufficient_confidence"]:
                                reasons[reason] += 1
                        self.mark(url, "rejected", "stop_filter")
                    if article.event_id:
                        from .fallback import extract, project_name

                        for name in project_name(article):
                            if normalize(name) == normalize(analysis.name):
                                continue
                            extra_analysis = extract(article, names=[name])
                            if extra_analysis is None:
                                continue
                            try:
                                self.persist(extra_analysis, [article], start, allow_shared_source=True)
                                with self.factory.begin() as session:
                                    row = session.get(Candidate, url)
                                    row.project_ids = list(dict.fromkeys([*(row.project_ids or []), self.last_project_id]))
                                if self.last_persist_visible:
                                    counts["new_projects" if self.last_newly_published else "duplicates"] += 1
                                    counts["event_projects"] += int(self.last_newly_published)
                            except AnalysisError:
                                logger.info("event_project_candidate_unverified")
                except (FetchError, AnalysisError) as exc:
                    code = str(exc)
                    if isinstance(exc, AnalysisError) and code == "not_a_verified_uzbekistan_project":
                        self.mark(url, "rejected", "not_project")
                        reasons["not_project"] += 1
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                        bucket["rejected"] += 1
                    else:
                        self.mark(url, "error", code)
                        if isinstance(exc, AnalysisError):
                            key = "translation_errors" if "translation" in code else "ai_errors"
                            counts[key] += 1
                            stage = "translation" if key == "translation_errors" else "ai"
                        errors.append({"source": url, "stage": stage, "code": code})
                        reasons[
                            "blocked_source"
                            if code.startswith("http_") or "robots" in code
                            else "parser_failure"
                            if stage == "parser"
                            else code
                        ] += 1
                except Exception:
                    logger.error("candidate_processing_failed")
                    self.mark(url, "error", "processing_failed")
                    errors.append({"source": url, "stage": stage, "code": "processing_failed"})
            details.update(reject_reasons=dict(reasons), origins={k: dict(v) for k, v in origins.items()})
            status = "partial" if errors or counts["pending"] else "completed"
        except Exception:
            logger.error("pipeline_failed")
            errors.append({"source": "Tizim", "stage": "pipeline", "code": "pipeline_failed"})
        finally:
            details["summary"] = summarize_run(counts, errors, bool(self.settings.ai_key))
            with self.factory.begin() as session:
                run = session.get(Run, run_id)
                run.finished_at, run.status = now_utc(), status
                run.counts, run.errors, run.details = counts.copy(), errors[:100], details
                run.duration_seconds = round(monotonic() - began, 2)
                self.release(session, owner)
        return {"id": run_id, "status": status, "counts": counts, "errors": errors[:100], "details": details}

    def mark(self, url, state, reason):
        with self.factory.begin() as session:
            candidate = session.get(Candidate, url)
            if candidate:
                candidate.status, candidate.reason, candidate.updated_at = state, reason, now_utc()
                if state == "rejected" and reason != "stop_filter":
                    record_rejection(session, url, candidate.article.get("title", ""), [reason])
                elif state in ("published", "event", "ecosystem"):
                    row = session.get(RejectedCandidate, url)
                    if row:
                        session.delete(row)
