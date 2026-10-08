from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import String, cast, func, or_, select, text
from .registry import seed_registry
from .evidence import audit_existing
from .radar_api import radar_status, sector_stats, evidence_json
from .sectors import SECTORS, LEGACY
from .config import Settings
from .dates import TASHKENT, today_start
from .db import (Candidate, EcosystemSignal, Problem, ProblemEvidence, Project,
                 ProjectProblemLink, Run, SolutionIdea, aware, make_db, now_utc)
from .scheduler import make_scheduler
from .schemas import CATEGORIES
from .intelligence import migrate_existing_problems
from .intelligence_api import dashboard, idea_json, problem_json, sector_intelligence, signal_json, status_extra


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
        summary_uz=content["summary_uz"],
        audience_groups=content.get("audience_groups", []),
        first_seen=iso(project.first_seen),
        last_seen=iso(project.last_seen),
        published_at=iso(project.published_at),
        images=project.images,
        primary_sector=project.primary_sector,
        sectors=project.sectors,
        real_project_confidence=project.real_project_confidence,
        source_count=len(project.sources),
        analysis_mode=content["analysis_mode"],
        rating_method="ai" if content["analysis_mode"] == "ai" else "deterministic_fallback",
        problem_statement=project.problem_statement,
        problem_subject=project.problem_subject,
        problem_scope=project.problem_scope,
        problem_gate_status=project.problem_gate_status,
        problem_gate_reason=project.problem_gate_reason,
        opportunity_score=project.opportunity_score,
        opportunity_grade=project.opportunity_grade,
        opportunity_details={"groups": (project.opportunity_details or {}).get("groups", {})},
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
    engine, factory = make_db(settings.database_url)
    seed_registry(factory, settings.sources_file)
    audit_existing(factory, settings.evidence_min_score)
    migrate_existing_problems(factory)
    scheduler = make_scheduler(settings, factory)

    @asynccontextmanager
    async def lifespan(app):
        if settings.scheduler_enabled:
            scheduler.start()
        yield
        if scheduler.running:
            scheduler.shutdown(wait=True)
        engine.dispose()

    app = FastAPI(title="O‘zbekiston loyihalari", lifespan=lifespan)
    app.state.factory, app.state.scheduler = factory, scheduler

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
        return {"status": "ok", "stage": "Uzbekistan"}

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
        city: str = "",
        audience: Literal["", "individual", "business", "both", "unknown"] = "",
        period: Literal["all", "today", "7d", "30d"] = "today",
        year: int | None = Query(default=None, ge=2022, le=2100),
        min_rating: float = Query(default=0, ge=0, le=10),
        grade: str = "",
        problem_scope: str = "",
        min_evidence: float = Query(default=0, ge=0, le=10),
        sort: Literal["date", "rating", "confidence", "usefulness"] = "date",
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=12, ge=1, le=50),
    ):
        query = select(Project).where(Project.visible.is_(True))
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
        if country:
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
        if period == "today":
            query = query.where(Project.first_seen >= today_start(now))
        elif period in ("7d", "30d"):
            query = query.where(Project.first_seen >= now - timedelta(days=7 if period == "7d" else 30))
        if year:
            query = query.where(
                Project.published_at >= datetime(year, 1, 1, tzinfo=timezone.utc),
                Project.published_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc),
            )
        order = {
            "date": Project.first_seen,
            "rating": Project.rating,
            "usefulness": Project.rating,
            "confidence": Project.confidence,
        }[sort]
        with factory() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            items = session.scalars(
                query.order_by(order.desc(), Project.id).offset((page - 1) * page_size).limit(page_size)
            ).all()
            return {
                "items": [serialize_project(p) for p in items],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @app.get("/api/projects/{project_id}")
    def project_detail(project_id: str):
        with factory() as session:
            project = session.get(Project, project_id)
            if project is None or not project.visible:
                raise HTTPException(404, "Loyiha topilmadi")
            result = serialize_project(project, detail=True)
            links = session.scalars(select(ProjectProblemLink).where(ProjectProblemLink.project_id == project_id)).all()
            result["related_problems"] = [{"id": problem.id, "title_uz": problem.title_uz}
                                          for link in links if (problem := session.get(Problem, link.problem_id))]
            return result

    @app.get("/api/status")
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
            total = session.scalar(select(func.count()).select_from(Project).where(Project.visible.is_(True)))
            today = session.scalar(
                select(func.count())
                .select_from(Project)
                .where(Project.first_seen >= today_start(now_utc()), Project.visible.is_(True))
            )
            pending = session.scalar(
                select(func.count()).select_from(Candidate).where(Candidate.status == "pending")
            )
            radar = radar_status(session, settings.evidence_min_score)
            intelligence = status_extra(session)
        job = scheduler.get_job("discovery")
        next_run = getattr(job, "next_run_time", None) if settings.scheduler_enabled else None
        return {
            "timezone": "Asia/Tashkent",
            "scheduler_enabled": settings.scheduler_enabled,
            "next_run": iso(next_run),
            "last_run": serialized[0] if serialized else None,
            "runs": serialized,
            "total_projects": total,
            "today_projects": today,
            "pending_candidates": pending,
            "ai_enabled": bool(settings.ai_key),
            "search_enabled": bool(settings.search_api_key.get_secret_value()),
            **radar,
            **intelligence,
        }

    @app.get("/api/intelligence/dashboard")
    def intelligence_dashboard():
        with factory() as session:
            return dashboard(session)

    @app.get("/api/problems")
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

    @app.get("/api/problems/{problem_id}")
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

    @app.get("/api/ideas")
    def ideas(period: Literal["all", "today", "7d", "30d"] = "all", year: int | None = Query(None, ge=2022, le=2100)):
        query = recent_period(select(SolutionIdea), SolutionIdea.created_at, period)
        if year:
            query = query.where(SolutionIdea.created_at >= datetime(year, 1, 1, tzinfo=timezone.utc), SolutionIdea.created_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc))
        with factory() as session:
            return [idea_json(i) for i in session.scalars(query.order_by(SolutionIdea.created_at.desc()).limit(100))]

    @app.get("/api/ideas/{idea_id}")
    def idea_detail(idea_id: str):
        with factory() as session:
            idea = session.get(SolutionIdea, idea_id)
            if not idea:
                raise HTTPException(404, "Yechim g‘oyasi topilmadi")
            return idea_json(idea)

    @app.get("/api/signals")
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

    @app.get("/api/sectors/intelligence")
    def sectors_intelligence():
        with factory() as session:
            return sector_intelligence(session)

    @app.get("/api/sectors/stats")
    def sectors_stats():
        with factory() as session:
            return sector_stats(session)

    @app.get("/api/sources")
    def source_registry():
        with factory() as session:
            return radar_status(session, settings.evidence_min_score)["sources"]

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
