from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hmac
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import String, cast, func, or_, select, text
from .registry import seed_registry
from .evidence import audit_existing
from .radar_api import radar_status, sector_stats, evidence_json
from .sectors import SECTORS, LEGACY
from .config import Settings
from .dates import TASHKENT, today_start
from .db import (Candidate, DatabaseIdentity, EcosystemSignal, Problem, ProblemEvidence, Project,
                 ProjectDeepAnalysis, ProjectProblemLink, ProviderHealth, RawDiscovery, RegistrySource, Run,
                 SchedulerCheckpoint, SourceBlock,
                 SolutionIdea, aware, make_db, now_utc)
from .llm_service import LLMService
from .writer import writer_session, writer_scope, WriterBusy
from .scheduler import make_scheduler
from .schemas import CATEGORIES
from .intelligence import migrate_existing_problems
from .intelligence_api import dashboard, idea_json, problem_json, sector_intelligence, signal_json, status_extra
from .signal_quality import audit_signals
from .publication import lifecycle_stage, synchronize_candidate_publication
from .catalog_ranking import rank as catalog_rank
from .geography import project_scope, section_reason
from .daily import publication_summary


def usable_images(images):
    """Reject obvious publisher artwork, trackers and known tiny images."""
    blocked = ("logo", "social-share", "social_share", "share-image", "favicon", "icon", "pixel", "banner", "advert")
    return [item for item in images or [] if item.get("url", "").startswith("https://")
            and not any(word in item["url"].lower() for word in blocked)
            and (not item.get("width") or item["width"] >= 160)
            and (not item.get("height") or item["height"] >= 90)]


def iso(value):
    return aware(value).isoformat() if value else None


def recent_period(query, column, period):
    if period == "today":
        return query.where(column >= today_start(now_utc()))
    if period in ("7d", "30d"):
        return query.where(column >= now_utc() - timedelta(days=7 if period == "7d" else 30))
    return query


def serialize_project(project, detail=False):
    content = project.content
    result = {
        field: getattr(project, field)
        for field in (
            "id",
            "name",
            "creator",
            "organization",
            "city",
            "event",
            "country",
            "category",
            "audience",
            "rating",
            "confidence",
        )
    }
    result.update(
        scope=project_scope(project),
        section_reason=section_reason(project),
        summary_uz=content.get("summary_uz", ""),
        short_description=project.short_description or content.get("summary_uz", ""),
        catalog_score=project.catalog_score,
        catalog_scores=project.catalog_scores or {},
        score_pending=project.score_pending,
        evidence_count=project.evidence_count,
        classification_confidence=project.classification_confidence,
        description_needs_translation=project.description_needs_translation,
        date_estimated=project.date_estimated,
        project_type=project.project_type,
        project_stage=project.project_stage,
        analysis_method=project.analysis_method,
        audience_groups=content.get("audience_groups", []),
        first_seen=iso(project.first_seen),
        last_seen=iso(project.last_seen),
        published_at=iso(project.published_at),
        images=usable_images(project.images),
        primary_sector=project.primary_sector,
        sectors=project.sectors,
        real_project_confidence=project.real_project_confidence,
        source_count=len(project.sources),
        analysis_mode=content.get("analysis_mode", project.analysis_method),
        rating_method=(project.analysis_method if project.analysis_method != "legacy" else
                       "ai" if content.get("analysis_mode") == "ai" else "deterministic_fallback"),
        problem_statement=project.problem_statement,
        problem_subject=project.problem_subject,
        problem_scope=project.problem_scope,
        problem_gate_status=project.problem_gate_status,
        problem_gate_reason=project.problem_gate_reason,
        opportunity_score=project.opportunity_score,
        opportunity_grade=project.opportunity_grade,
        opportunity_details={"groups": (project.opportunity_details or {}).get("groups", {})},
        publication_status=project.publication_status,
        lifecycle_stage=lifecycle_stage(project),
        solution_uz=(content.get("how_uz") or content.get("what_uz") or ""),
        primary_evidence_url=project.evidence_records[0].url if project.evidence_records else None,
        official_url=project.main_url,
        discovery_source_url=project.discovery_source_url,
    )
    if detail:
        result.update(
            content=content,
            evidence=evidence_json(project),
            detection_signals=project.detection_signals,
            main_url=project.main_url,
            aliases=project.aliases,
            rating_components=project.rating_components,
            confidence_components=project.confidence_components,
            opportunity_details=project.opportunity_details,
            secondary_problems=project.secondary_problems or [],
            sector_method=project.sector_method,
            project_type_method=project.project_type_method,
            publication_method=project.publication_method,
            score_reasons=project.catalog_score_reasons or {},
            sources=[
                {
                    "url": s.url,
                    "publisher": s.publisher,
                    "kind": s.kind,
                    "published_at": iso(s.published_at),
                    "quotes": s.quotes,
                }
                for s in project.sources
            ],
        )
    return result


def create_app(settings=None):
    settings = settings or Settings()
    engine, factory = make_db(settings.database_url, auto_migrate=settings.database_auto_migrate)
    if settings.startup_data_updates_enabled:
        with writer_scope(factory):
            seed_registry(factory, settings.sources_file)
            audit_existing(factory, settings.evidence_min_score)
            audit_signals(factory)
            migrate_existing_problems(factory)
            synchronize_candidate_publication(factory, settings)
    scheduler = make_scheduler(settings, factory)

    @asynccontextmanager
    async def lifespan(app):
        if settings.scheduler_enabled:
            scheduler.start()
        yield
        if scheduler.running:
            scheduler.shutdown(wait=True)
        engine.dispose()

    app = FastAPI(title="izlanish loyihalari", lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                           allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
                           allow_headers=["Content-Type", "X-Admin-Key"], allow_credentials=False)
    app.state.factory, app.state.scheduler = factory, scheduler

    @app.exception_handler(WriterBusy)
    async def writer_busy_handler(request, exc):
        return JSONResponse({"detail": "Qidiruv ishlamoqda. Keyinroq qayta urinib ko‘ring."}, status_code=409)

    def require_admin(x_admin_key: str = Header(default="")):
        expected = settings.admin_api_key.get_secret_value()
        if not expected:
            raise HTTPException(503, "Admin kaliti sozlanmagan")
        if not hmac.compare_digest(x_admin_key, expected):
            raise HTTPException(401, "Admin kaliti noto‘g‘ri")

    @app.middleware("http")
    async def secure_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/api/health")
    def health():
        with factory() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "stage": "Uzbekistan and Global"}

    @app.get("/api/meta")
    def meta():
        return {
            "categories": SECTORS,
            "sectors": SECTORS,
            "timezone": "Asia/Tashkent",
            "years": list(range(now_utc().astimezone(TASHKENT).year, 2021, -1)),
        }

    @app.get("/api/projects")
    def projects(
        q: str = Query(default="", max_length=200),
        category: str = "",
        country: str = "",
        archive: bool = False,
        city: str = "",
        audience: Literal["", "individual", "business", "both", "unknown"] = "",
        period: Literal["all", "today", "7d", "30d"] = "all",
        year: int | None = Query(default=None, ge=2022, le=2100),
        min_rating: float = Query(default=0, ge=0, le=10),
        grade: str = "",
        problem_scope: str = "",
        min_evidence: float = Query(default=0, ge=0, le=10),
        sort: Literal["date", "rating", "confidence", "usefulness", "catalog"] = "date",
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=12, ge=1, le=50),
    ):
        query = select(Project).where(Project.publication_status == "PUBLISHED")
        if q.strip():
            term = q.strip()
            query = query.where(
                or_(
                    *[
                        column.icontains(term, autoescape=True)
                        for column in (Project.name, Project.creator, Project.organization, Project.city)
                    ],
                    Project.content["summary_uz"].as_string().icontains(term, autoescape=True),
                    Project.content["keywords"].as_string().icontains(term, autoescape=True),
                    Project.category.in_([k for k, v in CATEGORIES.items() if term.lower() in v.lower()]),
                )
            )
        if category:
            sector = LEGACY.get(category, category)
            query = query.where(
                or_(
                    Project.primary_sector == sector,
                    cast(Project.sectors, String).contains('"' + sector + '"', autoescape=True),
                )
            )
        scope_filter = country in {"global", "Uzbekistan", "github", "boshqa"}
        if country and not scope_filter:
            query = query.where(Project.country == country)
        if city:
            query = query.where(Project.city.icontains(city, autoescape=True))
        if audience:
            query = query.where(
                Project.audience.in_(
                    [audience, "both"] if audience in ("individual", "business") else [audience]
                )
            )
        if min_rating:
            query = query.where(Project.rating >= min_rating)
        if grade:
            query = query.where(Project.opportunity_grade == grade)
        if problem_scope:
            query = query.where(Project.problem_scope == problem_scope)
        if min_evidence:
            query = query.where(Project.confidence >= min_evidence)
        now = now_utc()
        if archive:
            # Archive is a date view, never a holding area for uncertain classification.
            query = query.where(Project.published_at < today_start(now) - timedelta(days=2))
        if period == "today":
            query = query.where(Project.published_at >= today_start(now), Project.date_estimated.is_(False))
        elif period in ("7d", "30d"):
            query = query.where(Project.published_at >= now - timedelta(days=7 if period == "7d" else 30),
                                Project.date_estimated.is_(False))
        if year:
            query = query.where(
                Project.published_at >= datetime(year, 1, 1, tzinfo=TASHKENT).astimezone(timezone.utc),
                Project.published_at < datetime(year + 1, 1, 1, tzinfo=TASHKENT).astimezone(timezone.utc),
            )
        order = {
            "date": Project.published_at,
            "rating": Project.rating,
            "usefulness": Project.rating,
            "confidence": Project.confidence,
            "catalog": Project.published_at,
        }[sort]
        with factory() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            if sort == "catalog" or scope_filter:
                all_items = session.scalars(query).all()
                if scope_filter:
                    wanted = {"global": "Global", "github": "GitHub", "Uzbekistan": "Uzbekistan", "boshqa": "Boshqa"}[country]
                    all_items = [project for project in all_items if project_scope(project) == wanted]
                    total = len(all_items)
            if sort == "catalog":
                items = sorted(all_items, key=lambda project: (
                    catalog_rank(project, neutral=settings.catalog_neutral_rank),
                    aware(project.published_at), project.id), reverse=True)[(page - 1) * page_size:page * page_size]
            elif scope_filter:
                items = sorted(all_items, key=lambda project: (
                    aware(project.published_at) if sort == "date" else getattr(project, order.key),
                    project.id), reverse=True)[(page - 1) * page_size:page * page_size]
            else:
                items = session.scalars(
                    query.order_by(order.desc(), Project.id).offset((page - 1) * page_size).limit(page_size)
                ).all()
            return {
                "items": [serialize_project(p) for p in items],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @app.get("/api/catalog/home")
    def catalog_home():
        with factory() as session:
            all_items = session.scalars(select(Project).where(Project.publication_status == "PUBLISHED")).all()
            now = now_utc()
            today = today_start(now)
            eligible = [project for project in all_items if not project.date_estimated and
                        aware(project.published_at) < today + timedelta(days=1)]
            fresh_period = "empty"
            fresh = []
            for label, start in (("today", today), ("yesterday", today - timedelta(days=1)),
                                 ("three_days", today - timedelta(days=2))):
                previous = today if label == "yesterday" else None
                fresh = [project for project in eligible if aware(project.published_at) >= start and
                         (previous is None or aware(project.published_at) < previous)]
                if fresh:
                    fresh_period = label
                    break
            ordered = sorted(fresh, key=lambda project: (aware(project.published_at), project.id), reverse=True)
            local = [project for project in ordered if project_scope(project) == "Uzbekistan"]
            global_items = [project for project in ordered if project_scope(project) == "Global"]
            github_items = [project for project in ordered if project_scope(project) == "GitHub"]
            sections = {section: 0 for section in ("Uzbekistan", "Global", "GitHub", "Boshqa")}
            for project in all_items:
                sections[project_scope(project)] += 1
            sectors = {}
            for project in all_items:
                key = project.primary_sector or "Other"
                bucket = sectors.setdefault(key, {"sector": key, "projects": 0, "scored": 0, "sum_score": 0.0})
                bucket["projects"] += 1
                if project.catalog_score is not None:
                    bucket["scored"] += 1
                    bucket["sum_score"] += project.catalog_score
            return {
                "total": len(all_items),
                "uzbekistan_total": sections["Uzbekistan"],
                "global_total": sections["Global"],
                "github_total": sections["GitHub"],
                "boshqa_total": sections["Boshqa"],
                "fresh_period": fresh_period,
                "top": [serialize_project(project) for project in ordered[:6]],
                "uzbekistan": [serialize_project(project) for project in local[:4]],
                "global": [serialize_project(project) for project in global_items[:4]],
                "github": [serialize_project(project) for project in github_items[:4]],
                "sectors": [{"sector": value["sector"], "projects": value["projects"],
                             "average_catalog_score": round(value["sum_score"] / value["scored"], 1)
                             if value["scored"] else None}
                            for value in sorted(sectors.values(), key=lambda value: (-value["projects"], value["sector"]))],
            }

    @app.get("/api/catalog/facets")
    def catalog_facets():
        with factory() as session:
            items = session.scalars(select(Project).where(Project.publication_status == "PUBLISHED")).all()
            sections = {section: 0 for section in ("Uzbekistan", "Global", "GitHub", "Boshqa")}
            years = {}
            for project in items:
                sections[project_scope(project)] += 1
                year = str(aware(project.published_at).astimezone(TASHKENT).year)
                years[year] = years.get(year, 0) + 1
            return {"total": len(items), "sections": sections, "years": years}

    @app.get("/api/projects/{project_id}")
    def project_detail(project_id: str):
        with factory() as session:
            project = session.get(Project, project_id)
            if project is None or project.publication_status != "PUBLISHED":
                raise HTTPException(404, "Loyiha topilmadi")
            result = serialize_project(project, detail=True)
            deep = session.get(ProjectDeepAnalysis, project_id)
            if deep and deep.criteria:
                result["deep_analysis"] = {"criteria": deep.criteria,
                                           "weighted_score": deep.weighted_score,
                                           "weights_version": deep.weights_version}
            links = session.scalars(select(ProjectProblemLink).where(ProjectProblemLink.project_id == project_id)).all()
            result["related_problems"] = [{"id": problem.id, "title_uz": problem.title_uz}
                                          for link in links if (problem := session.get(Problem, link.problem_id))]
            return result

    @app.get("/api/admin/status", dependencies=[Depends(require_admin)])
    @app.get("/api/status", dependencies=[Depends(require_admin)], include_in_schema=False)
    def status():
        with factory() as session:
            runs = session.scalars(select(Run).order_by(Run.id.desc()).limit(10)).all()
            serialized = [
                {
                    "id": r.id,
                    "started_at": iso(r.started_at),
                    "details": r.details,
                    "finished_at": iso(r.finished_at),
                    "status": r.status,
                    "counts": r.counts,
                    "errors": r.errors,
                    "duration_seconds": r.duration_seconds,
                }
                for r in runs
            ]
            total = session.scalar(select(func.count()).select_from(Project).where(Project.publication_status == "PUBLISHED"))
            today = session.scalar(
                select(func.count())
                .select_from(Project)
                .where(Project.published_at >= today_start(now_utc()), Project.publication_status == "PUBLISHED")
            )
            pending = session.scalar(
                select(func.count()).select_from(Candidate).where(Candidate.status == "pending")
            )
            raw_counts = {state: amount for state, amount in session.execute(
                select(RawDiscovery.status, func.count()).group_by(RawDiscovery.status)).all()}
            deep_counts = {state: amount for state, amount in session.execute(
                select(ProjectDeepAnalysis.status, func.count()).group_by(ProjectDeepAnalysis.status)).all()}
            telegram_checkpoints = [{"channel": row.name.removeprefix("telegram:"),
                                     "last_success_at": iso(row.last_success_at),
                                     "last_message_id": (row.cursor or {}).get("last_id")}
                                    for row in session.scalars(select(SchedulerCheckpoint).where(
                                        SchedulerCheckpoint.name.startswith("telegram:")))]
            blocked_sources = []
            for source_id in session.scalars(select(SourceBlock.source_id).distinct()):
                last = session.scalar(select(SourceBlock).where(SourceBlock.source_id == source_id)
                                      .order_by(SourceBlock.id.desc()))
                if last and last.action == "BLOCK":
                    blocked_sources.append({"source_id": source_id, "at": iso(last.at), "reason": last.reason})
            provider_rows = {row.name: row for row in session.scalars(select(ProviderHealth))}
            daily_publication = publication_summary(session, settings)
            public_sections = {"Uzbekistan": 0, "Global": 0, "GitHub": 0, "Boshqa": 0}
            for project in session.scalars(select(Project).where(Project.publication_status == "PUBLISHED")):
                public_sections[project_scope(project)] += 1
            provider_status = []
            for configured in LLMService(settings).status():
                health = provider_rows.get(configured["name"])
                provider_status.append({"name": configured["name"], "model": configured["model"],
                                        "configured": configured["configured"],
                                        "healthy": not health or health.consecutive_failures < settings.llm_circuit_breaker_failures,
                                        "requests": health.requests if health else 0,
                                        "successes": health.successes if health else 0,
                                        "timeouts": health.timeouts if health else 0,
                                        "rate_limits": health.rate_limits if health else 0,
                                        "quota_errors": health.quota_errors if health else 0,
                                        "invalid_json": health.invalid_json if health else 0,
                                        "schema_failures": health.schema_failures if health else 0,
                                        "fallback_count": health.fallback_count if health else 0,
                                        "average_latency_ms": round(health.latency_total_ms / health.requests, 1)
                                        if health and health.requests else None,
                                        "last_success_at": iso(health.last_success_at) if health else None,
                                        "last_error": health.last_error if health else ""})
            radar = radar_status(session, settings.evidence_min_score)
            intelligence = status_extra(session)
            from .free_budget import free_status
            free_daily = free_status(session, settings)
        job = scheduler.get_job("discovery")
        next_run = getattr(job, "next_run_time", None) if settings.scheduler_enabled else None
        daily_job = scheduler.get_job("daily_processing")
        next_daily_processing = getattr(daily_job, "next_run_time", None) if settings.scheduler_enabled else None
        return {
            "timezone": "Asia/Tashkent",
            "free_daily": free_daily,
            "scheduler_enabled": settings.scheduler_enabled,
            "next_run": iso(next_run),
            "next_daily_processing": iso(next_daily_processing),
            "last_run": serialized[0] if serialized else None,
            "runs": serialized,
            "total_projects": total,
            "today_projects": today,
            "daily_publication": daily_publication,
            "database_instance_id": session.get(DatabaseIdentity, "primary").instance_uuid,
            "database_driver": engine.dialect.name,
            "public_sections": public_sections,
            "last_stop_reason": (serialized[0]["details"] or {}).get("stop_reason", "") if serialized else "",
            "pending_candidates": pending,
            "ai_enabled": LLMService(settings).available,
            "llm_provider_order": [item["name"] for item in provider_status],
            "llm_providers": provider_status,
            "raw_discoveries": raw_counts,
            "deep_analysis": deep_counts,
            "telegram_channels": telegram_checkpoints,
            "blocked_sources": blocked_sources,
            "telegram_ingestion_configured": bool(settings.telegram_api_id and
                                                   settings.telegram_api_hash.get_secret_value() and
                                                   settings.telegram_session.get_secret_value()),
            "telegram_alerts_configured": bool(settings.telegram_bot_token.get_secret_value() and
                                               settings.admin_telegram_chat_id),
            "search_enabled": bool(settings.search_api_key.get_secret_value()),
            **radar,
            **intelligence,
        }

    @app.get("/api/admin/review", dependencies=[Depends(require_admin)])
    def review_queue(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
        with factory() as session:
            query = select(Candidate).where(Candidate.status.in_(["pending", "review_required", "error"]))
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(query.order_by(Candidate.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
            return {"total": total, "items": [{
                "url": c.url, "title": (c.article or {}).get("title", ""), "source_id": c.source_id,
                "status": c.status, "reason": c.reason, "detector_result": c.detector_result,
                "creator": next((p.creator for pid in c.project_ids or [] if (p := session.get(Project, pid))), "") or next((e.get("creator") for e in (c.article or {}).get("_catalog_entries", []) if e.get("creator")), ""),
                "canonical_project": next((p.name for pid in c.project_ids or [] if (p := session.get(Project, pid))), "") or next((e.get("name") for e in (c.article or {}).get("_catalog_entries", []) if e.get("name")), ""),
                "primary_problem": next((p.problem_statement for pid in c.project_ids or [] if (p := session.get(Project, pid))), ""),
                "evidence": next(([{"url": e.url, "type": e.evidence_type, "quote": e.quote} for e in p.evidence_records[:5]] for pid in c.project_ids or [] if (p := session.get(Project, pid))), []),
                "confidence": next((p.confidence for pid in c.project_ids or [] if (p := session.get(Project, pid))), None),
                "review_decision": c.review_decision,
                "classification_confidence": c.classification_confidence,
                "classification_history": c.classification_history,
                "status_history": c.status_history,
                "publication_method": next((p.publication_method for pid in c.project_ids or [] if (p := session.get(Project, pid))), ""),
                "analysis_method": c.analysis_mode,
            } for c in rows]}

    @app.post("/api/admin/review/action", dependencies=[Depends(require_admin)])
    def review_action(url: str, action: Literal["ACCEPT", "REJECT", "KEEP_FOR_REVIEW"], reason: str = ""):
        allowed = {"not_project", "no_meaningful_problem", "minor_feature", "duplicate", "insufficient_evidence", "missing_creator", "signal_only", "irrelevant", "old_irrelevant_content", "other"}
        if action == "REJECT" and reason not in allowed:
            raise HTTPException(422, "Rad etish sababi kerak")
        with writer_session(factory) as session:
            candidate = session.get(Candidate, url)
            if not candidate or candidate.status not in {"pending", "review_required", "error"}:
                raise HTTPException(404, "Ko‘rib chiqiladigan nomzod topilmadi")
            candidate.review_decision = action
            candidate.updated_at = now_utc()
            if action == "REJECT":
                candidate.status, candidate.reason = "rejected", reason
                from .evidence import record_rejection
                record_rejection(session, url, (candidate.article or {}).get("title", ""), [reason])
            elif action == "ACCEPT":
                # Acceptance means eligible for the normal pipeline, not publication.
                candidate.status, candidate.reason = "queued", "admin_recheck"
            else:
                candidate.status, candidate.reason = "review_required", reason or candidate.reason
        return {"url": url, "action": action, "status": candidate.status, "reason": candidate.reason}

    @app.get("/api/admin/projects/{project_id}", dependencies=[Depends(require_admin)])
    def admin_project(project_id: str):
        with factory() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise HTTPException(404, "Loyiha topilmadi")
            return {**serialize_project(project, detail=True),
                    "classification_history": project.classification_history,
                    "status_history": project.status_history,
                    "attribute_history": project.attribute_history,
                    "review_reason": project.review_reason,
                    "publication_excerpt": project.publication_excerpt,
                    "reanalysis_state": project.reanalysis_state}

    @app.get("/api/admin/catalog", dependencies=[Depends(require_admin)])
    def admin_catalog(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                      section: Literal["", "Boshqa"] = ""):
        with factory() as session:
            query = select(Project).order_by(Project.first_seen.desc())
            if section:
                matching = [project for project in session.scalars(query) if project_scope(project) == section]
                total = len(matching)
                rows = matching[(page - 1) * page_size:page * page_size]
            else:
                total = session.scalar(select(func.count()).select_from(Project))
                rows = session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
            return {"total": total, "items": [{"id": project.id, "name": project.name,
                    "status": project.publication_status, "reason": project.publication_reason,
                    "method": project.publication_method, "analysis_method": project.analysis_method,
                    "scope": project_scope(project), "section_reason": section_reason(project),
                    "source_count": len(project.sources)} for project in rows]}

    @app.post("/api/admin/projects/{project_id}/section", dependencies=[Depends(require_admin)])
    def admin_project_section(project_id: str, section: Literal["Uzbekistan", "Global", "GitHub", "Boshqa"],
                              reason: str = Query(min_length=3, max_length=200)):
        from .catalog_store import history
        with writer_session(factory) as session:
            project = session.get(Project, project_id)
            if project is None:
                raise HTTPException(404, "Loyiha topilmadi")
            if not reason.strip():
                raise HTTPException(422, "Bo‘lim sababi kerak")
            previous = project_scope(project)
            project.catalog_section_override = section
            project.catalog_section_reason = reason.strip()
            project.attribute_history = history(project.attribute_history, section, "admin_section",
                                                f"{previous}: {reason.strip()}", now_utc())
            return {"id": project.id, "scope": project_scope(project), "reason": reason.strip()}

    @app.post("/api/admin/projects/{project_id}/action", dependencies=[Depends(require_admin)])
    def admin_project_action(project_id: str, action: Literal["PUBLISH", "HIDE", "REJECT", "MERGE"],
                             reason: str = "", target_id: str = ""):
        from .catalog_admin import catalog_action
        with writer_session(factory) as session:
            try:
                return catalog_action(session, project_id, action, reason, target_id, settings)
            except ValueError as exc:
                raise HTTPException(404 if str(exc) == "project_not_found" else 422, str(exc)) from exc

    @app.get("/api/intelligence/dashboard")
    def intelligence_dashboard():
        with factory() as session:
            data = dashboard(session)
            return {
                "today": {key: data["today"][key] for key in ("sources_checked", "projects")},
                "total": {"projects": data["total"]["projects"]},
                "latest_projects": [
                    {key: item[key] for key in (
                        "id", "name", "problem", "solution", "affected_users",
                        "evidence_score", "country", "sector", "published_at", "source_count",
                    )}
                    for item in data["latest_projects"]
                ],
            }

    @app.get("/api/problems", dependencies=[Depends(require_admin)])
    def problems(scope: str = "", sector: str = "", country: str = "", period: Literal["all", "today", "7d", "30d"] = "all", year: int | None = Query(None, ge=2022, le=2100), min_evidence_level: int = Query(1, ge=1, le=5), page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50)):
        query = recent_period(select(Problem), Problem.first_seen_at, period)
        if scope:
            query = query.where(Problem.scope == scope)
        if sector:
            query = query.where(Problem.sector == sector)
        if country:
            query = query.where(Problem.country == country)
        if year:
            publication = func.coalesce(Problem.first_evidence_published_at, Problem.first_seen_at)
            query = query.where(publication >= datetime(year, 1, 1, tzinfo=timezone.utc), publication < datetime(year + 1, 1, 1, tzinfo=timezone.utc))
        query = query.where(Problem.evidence_level >= min_evidence_level)
        with factory() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(query.order_by(Problem.last_seen_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
            return {"items": [problem_json(p, session.scalar(select(func.count(func.distinct(ProblemEvidence.source_url))).where(ProblemEvidence.problem_id == p.id))) for p in rows], "total": total, "page": page}

    @app.get("/api/problems/{problem_id}", dependencies=[Depends(require_admin)])
    def problem_detail(problem_id: str):
        with factory() as session:
            p = session.get(Problem, problem_id)
            if not p:
                raise HTTPException(404, "Muammo topilmadi")
            evidence = session.scalars(select(ProblemEvidence).where(ProblemEvidence.problem_id == p.id)).all()
            links = session.scalars(select(ProjectProblemLink).where(ProjectProblemLink.problem_id == p.id)).all()
            ideas = session.scalars(select(SolutionIdea).where(SolutionIdea.problem_id == p.id)).all()
            return problem_json(p, len({e.source_url for e in evidence})) | {
                "evidence": [{"source_url": e.source_url, "quote": e.quote,
                              "evidence_type": e.evidence_type, "publication_date": iso(e.publication_date)} for e in evidence],
                "projects": [{"id": project.id, "name": project.name} for link in links
                             if (project := session.get(Project, link.project_id)) and project.visible],
                "ideas": [idea_json(i) for i in ideas],
            }

    @app.get("/api/ideas", dependencies=[Depends(require_admin)])
    def ideas(period: Literal["all", "today", "7d", "30d"] = "all", year: int | None = Query(None, ge=2022, le=2100)):
        query = recent_period(select(SolutionIdea), SolutionIdea.created_at, period)
        if year:
            query = query.where(SolutionIdea.created_at >= datetime(year, 1, 1, tzinfo=timezone.utc), SolutionIdea.created_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc))
        with factory() as session:
            return [idea_json(i) for i in session.scalars(query.order_by(SolutionIdea.created_at.desc()).limit(100))]

    @app.get("/api/ideas/{idea_id}", dependencies=[Depends(require_admin)])
    def idea_detail(idea_id: str):
        with factory() as session:
            idea = session.get(SolutionIdea, idea_id)
            if not idea:
                raise HTTPException(404, "Yechim g‘oyasi topilmadi")
            return idea_json(idea)

    @app.get("/api/signals", dependencies=[Depends(require_admin)])
    def signals(country: str = "", sector: str = "", signal_type: str = "", period: Literal["all", "today", "7d", "30d"] = "all", year: int | None = Query(None, ge=2022, le=2100)):
        query = recent_period(select(EcosystemSignal), EcosystemSignal.discovered_at, period)
        if country:
            query = query.where(EcosystemSignal.country == country)
        if sector:
            query = query.where(EcosystemSignal.sector == sector)
        if signal_type:
            query = query.where(EcosystemSignal.signal_type == signal_type)
        if year:
            query = query.where(EcosystemSignal.published_at >= datetime(year, 1, 1, tzinfo=timezone.utc), EcosystemSignal.published_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc))
        with factory() as session:
            return [signal_json(s) for s in session.scalars(query.order_by(EcosystemSignal.discovered_at.desc()).limit(100))]

    @app.get("/api/sectors/intelligence", dependencies=[Depends(require_admin)])
    def sectors_intelligence():
        with factory() as session:
            return sector_intelligence(session)

    @app.get("/api/sectors/stats", dependencies=[Depends(require_admin)])
    def sectors_stats():
        with factory() as session:
            return sector_stats(session)

    @app.get("/api/public/sources")
    def public_sources():
        with factory() as session:
            sources = session.scalars(select(RegistrySource).where(RegistrySource.enabled.is_(True)).order_by(RegistrySource.name)).all()
            return [{"id": s.id, "name": s.name, "url": s.url,
                     "group": "Global startup manbalari" if s.country and s.country != "Uzbekistan" else
                              "Universitetlar" if s.source_type == "university" else
                              "Tadbir va akseleratorlar" if s.source_type in {"hackathon", "event", "accelerator"} else
                              "Startap platformalari" if s.source_type == "startup_platform" else "Nashrlar va tashkilotlar"}
                    for s in sources if s.collection_method != "search"]

    @app.get("/api/admin/sources", dependencies=[Depends(require_admin)])
    @app.get("/api/sources", dependencies=[Depends(require_admin)], include_in_schema=False)
    def source_registry():
        with factory() as session:
            return radar_status(session, settings.evidence_min_score)["sources"]

    @app.get("/api/admin/source-yield", dependencies=[Depends(require_admin)])
    def source_yield():
        with factory() as session:
            candidates = list(session.scalars(select(Candidate)))
            projects = {p.id: p for p in session.scalars(select(Project))}
            result = []
            for source in session.scalars(select(RegistrySource).order_by(RegistrySource.priority.desc(), RegistrySource.id)):
                rows = [c for c in candidates if c.source_id == source.id]
                linked = {pid for c in rows for pid in c.project_ids or [] if pid in projects}
                linked.update(p.id for p in projects.values() if any(record.source_id == source.id for record in p.sources))
                reasons = {}
                for c in rows:
                    if c.status == "rejected":
                        reasons[c.reason] = reasons.get(c.reason, 0) + 1
                result.append({"source_id": source.id, "name": source.name, "enabled": source.enabled,
                               "items_fetched": source.candidates_found, "candidate_records": len(rows),
                               "raw_discoveries": session.scalar(select(func.count()).select_from(RawDiscovery).where(
                                   RawDiscovery.source_adapter == source.id)) or 0,
                               "pre_filtered": session.scalar(select(func.count()).select_from(RawDiscovery).where(
                                   RawDiscovery.source_adapter == source.id, RawDiscovery.failure_reason == "obvious_noise")) or 0,
                               "project_candidates": sum(c.detector_result in ("PROJECT_CANDIDATE", "PROJECT", "MULTI") for c in rows),
                               "verified_projects": sum(projects[pid].visible or projects[pid].publication_status == "PUBLISHED" for pid in linked),
                               "published_projects": sum(projects[pid].publication_status == "PUBLISHED" for pid in linked),
                               "rejected_items": sum(c.status == "rejected" for c in rows),
                               "dominant_rejection_reasons": sorted(reasons.items(), key=lambda pair: -pair[1])[:3]})
            return result

    if (settings.frontend_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Sahifa topilmadi")
        index = settings.frontend_dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {"message": "Frontendni yig‘ing: cd frontend && npm ci && npm run build"}, status_code=503
        )

    return app
