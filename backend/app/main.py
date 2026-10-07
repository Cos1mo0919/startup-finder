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
from .db import Candidate, Project, Run, aware, make_db, now_utc
from .scheduler import make_scheduler
from .schemas import CATEGORIES


def iso(value):
    return aware(value).isoformat() if value else None


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
        city: str = "",
        audience: Literal["", "individual", "business", "both", "unknown"] = "",
        period: Literal["all", "today", "7d", "30d"] = "today",
        year: int | None = Query(default=None, ge=2022, le=2100),
        min_rating: float = Query(default=0, ge=0, le=10),
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
            return serialize_project(project, detail=True)

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
        }

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
