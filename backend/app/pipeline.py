import logging
from datetime import timedelta
from time import monotonic
from uuid import uuid4
from sqlalchemy import and_, or_, select, update
from .analysis import AnalysisError, analyzer_for, validate_analysis
from .collectors.sources import Discovery
from .collectors.parsers import PARSER_VERSION
from .dates import valid_date
from .db import Candidate, EcosystemSignal, Lease, Project, RegistrySource, Run, Source, now_utc
from .dedup import find_duplicate, fingerprint
from .detection import material_type, normalize
from .network import FetchError, WebClient, canonical_url
from .ranking import score
from .evidence import attach_evidence, audit_existing, evaluate_project, record_rejection
from .events import save_event
from .registry import seed_registry
from .sectors import classify_sectors
from .schemas import Analysis, Article

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings, factory, discovery=None, analyzer=None):
        self.settings, self.factory = settings, factory
        self.web = None if discovery else WebClient(settings)
        self.discovery = discovery or Discovery(settings, self.web, factory=factory)
        self.analyzer = analyzer or analyzer_for(settings)
        seed_registry(factory, settings.sources_file)
        self.last_persist_visible = False

    def close(self):
        if self.web:
            self.web.close()

    def acquire(self, owner, now):
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
        now = now_utc()
        with self.factory.begin() as session:
            result = session.execute(
                update(Lease)
                .where(Lease.name == "pipeline", Lease.owner == owner, Lease.expires_at > now)
                .values(expires_at=now + timedelta(minutes=20))
            )
            if result.rowcount != 1:
                raise RuntimeError("pipeline_lease_lost")

    def persist(self, analysis, articles, now):
        validate_analysis(analysis, articles)
        # Retain only sources actually cited by validated facts.
        cited = {canonical_url(f.source_url) for f in analysis.facts}
        articles = [a for a in articles if canonical_url(a.url) in cited]
        with self.factory.begin() as session:
            project = find_duplicate(session, analysis, [a.url for a in articles])
            created = project is None
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
                    if previous.analysis_mode == "extractive" and analysis.analysis_mode == "ai"
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
            if not project.event_id and articles[0].event_id:
                project.event_id = articles[0].event_id
            known = {s.url for s in project.sources}
            for article in articles:
                url = canonical_url(article.url)
                if url not in known:
                    project.sources.append(
                        Source(
                            url=url,
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
            reasons = evaluate_project(session, project, self.settings.evidence_min_score)
            self.last_persist_visible = project.visible
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

    def run(self, archive=False):
        owner, start, began = str(uuid4()), now_utc(), monotonic()
        if not self.acquire(owner, start):
            return {"status": "busy"}
        counts = dict(
            sources_checked=0,
            candidates=0,
            rejected=0,
            duplicates=0,
            new_projects=0,
            pending=0,
            stop_filtered=0,
            ecosystem_signals=0,
            events=0,
            event_projects=0,
        )
        errors = []
        with self.factory.begin() as session:
            run = Run(started_at=start, counts=counts.copy())
            session.add(run)
            session.flush()
            run_id = run.id
        try:
            audit_existing(self.factory, self.settings.evidence_min_score)
            links, discovery_errors, checked = self.discovery.discover(start, archive)
            errors.extend(discovery_errors)
            if hasattr(self.discovery, "follow_events"):
                event_links, event_errors = self.discovery.follow_events(start)
                links = event_links + links
                errors.extend(event_errors)
            counts["sources_checked"] = checked
            with self.factory() as session:
                reanalysis = set()
                if self.settings.ai_key:
                    reanalysis = set(
                        session.scalars(
                            select(Source.url)
                            .join(Project)
                            .where(Project.content["analysis_mode"].as_string() == "extractive")
                        )
                    )
                pending = list(
                    session.scalars(
                        select(Candidate)
                        .where(
                            or_(
                                Candidate.status.in_(["pending", "error"]),
                                and_(
                                    Candidate.status.in_(["published", "rejected"]),
                                    Candidate.url.in_(reanalysis),
                                ),
                            )
                        )
                        .order_by(Candidate.updated_at)
                        .limit(self.settings.max_candidates)
                    )
                )
            retry = {c.url: c.article for c in pending}
            todo = [{"url": c.url, "cached": True} for c in pending] + links
            seen = set()
            for item in todo[: self.settings.max_candidates * 2]:
                self.heartbeat(owner)
                url = canonical_url(item["url"])
                if url in seen:
                    continue
                seen.add(url)
                with self.factory() as session:
                    existing = session.get(Candidate, url)
                    if existing and (
                        (existing.status in ("published", "ecosystem", "event") and url not in reanalysis)
                        or (
                            existing.status == "rejected"
                            and url not in reanalysis
                            and not (archive and existing.reason == "date_out_of_range")
                        )
                    ):
                        continue
                counts["candidates"] += 1
                try:
                    article = (
                        Article.model_validate(retry[url])
                        if item.get("cached") and retry[url].get("parser_version", 1) == PARSER_VERSION
                        else self.discovery.article(url, item.get("published_at"))
                    )
                    article.source_id = item.get("source_id") or article.source_id
                    article.event_id = item.get("event_id") or article.event_id
                    with self.factory.begin() as session:
                        candidate = session.get(Candidate, url)
                        if candidate is None:
                            candidate = Candidate(url=url, article=article.model_dump(mode="json"))
                            session.add(candidate)
                        candidate.source_id, candidate.event_id = article.source_id, article.event_id
                        candidate.article = article.model_dump(mode="json")
                        candidate.attempts = (candidate.attempts or 0) + 1
                    if not valid_date(article.published_at, start, archive):
                        self.mark(url, "rejected", "date_out_of_range")
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                        continue
                    event_id, event_created = save_event(self.factory, article, start)
                    counts["events"] += int(event_created)
                    classification = material_type(article)
                    if classification == "ECOSYSTEM_SIGNAL":
                        with self.factory.begin() as session:
                            if session.get(EcosystemSignal, url) is None:
                                session.add(
                                    EcosystemSignal(
                                        url=url,
                                        title=article.title,
                                        source_id=article.source_id,
                                        signal_type="ecosystem",
                                        published_at=article.published_at,
                                        quote=article.text[:1500],
                                        discovered_at=start,
                                    )
                                )
                        self.mark(url, "ecosystem", "")
                        counts["ecosystem_signals"] += 1
                        continue
                    if classification == "EVENT":
                        self.mark(url, "event", "")
                        continue
                    if classification != "PROJECT":
                        self.mark(
                            url, "rejected", "idea_list" if classification == "REJECT" else "not_project"
                        )
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                        continue
                    analysis = self.analyzer.analyze([article])
                    if analysis is None:
                        self.mark(url, "pending", "needs_ai_or_more_evidence")
                        counts["pending"] += 1
                        continue
                    articles = [article]
                    try:
                        for extra_url in self.discovery.corroborate(analysis.name, article.url):
                            counts["sources_checked"] += 1
                            try:
                                extra = self.discovery.article(extra_url)
                                if valid_date(extra.published_at, start, archive=True) and normalize(
                                    analysis.name
                                ) in normalize(extra.title + " " + extra.text):
                                    articles.append(extra)
                            except FetchError as exc:
                                errors.append({"source": "Qo‘shimcha manba", "code": str(exc)})
                        if len(articles) > 1:
                            combined = self.analyzer.analyze(articles)
                            if combined and normalize(combined.name) == normalize(analysis.name):
                                analysis = combined
                    except (FetchError, AnalysisError) as exc:
                        errors.append({"source": "Qo‘shimcha tahlil", "code": str(exc)})
                    created = self.persist(analysis, articles, start)
                    if self.last_persist_visible:
                        counts["new_projects" if created else "duplicates"] += 1
                        counts["event_projects"] += int(created and bool(article.event_id))
                        if created and article.source_id:
                            with self.factory.begin() as session:
                                source = session.get(RegistrySource, article.source_id)
                                if source:
                                    source.new_projects += 1
                        self.mark(url, "published", "")
                    else:
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                        self.mark(url, "rejected", "stop_filter")
                except (FetchError, AnalysisError) as exc:
                    if isinstance(exc, AnalysisError) and str(exc) == "not_a_verified_uzbekistan_project":
                        self.mark(url, "rejected", "not_a_project")
                        counts["rejected"] += 1
                        counts["stop_filtered"] += 1
                    else:
                        self.mark(url, "error", str(exc))
                        errors.append({"source": "Nomzod", "code": str(exc)})
                except Exception:
                    # Avoid logging raw payloads, URLs with query secrets or SDK credential-bearing exceptions.
                    logger.error("candidate_processing_failed")
                    self.mark(url, "error", "processing_failed")
                    errors.append({"source": "Nomzod", "code": "processing_failed"})
            status = "partial" if errors else "completed"
        except Exception:
            logger.error("pipeline_failed")
            status = "failed"
            errors.append({"source": "Tizim", "code": "pipeline_failed"})
        finally:
            with self.factory.begin() as session:
                run = session.get(Run, run_id)
                run.finished_at, run.status = now_utc(), status
                run.counts, run.errors = counts.copy(), errors[:50]
                run.duration_seconds = round(monotonic() - began, 2)
                session.execute(
                    update(Lease)
                    .where(Lease.name == "pipeline", Lease.owner == owner)
                    .values(expires_at=now_utc(), owner="")
                )
        return {"id": run_id, "status": status, "counts": counts, "errors": errors[:50]}

    def mark(self, url, state, reason):
        with self.factory.begin() as session:
            candidate = session.get(Candidate, url)
            if candidate:
                candidate.status, candidate.reason, candidate.updated_at = state, reason, now_utc()
                if state == "rejected" and reason != "stop_filter":
                    record_rejection(session, url, candidate.article.get("title", ""), [reason])
