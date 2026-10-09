from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hmac
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query
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
                 ProjectProblemLink, RegistrySource, Run, SolutionIdea, aware, make_db, now_utc)
from .scheduler import make_scheduler
from .schemas import CATEGORIES
from .intelligence import migrate_existing_problems
from .intelligence_api import dashboard, idea_json, problem_json, sector_intelligence, signal_json, status_extra
from .signal_quality import audit_signals
from .publication import lifecycle_stage, synchronize_candidate_publication


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
    audit_signals(factory)
    migrate_existing_problems(factory)
    synchronize_candidate_publication(factory)
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
    app.state.factory, app.state.scheduler = factory, scheduler

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
        city: str = "",
        audience: Literal["", "individual", "business", "both", "unknown"] = "",
        period: Literal["all", "today", "7d", "30d"] = "all",
        year: int | None = Query(default=None, ge=2022, le=2100),
        min_rating: float = Query(default=0, ge=0, le=10),
        grade: str = "",
        problem_scope: str = "",
        min_evidence: float = Query(default=0, ge=0, le=10),
        sort: Literal["date", "rating", "confidence", "usefulness"] = "date",
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
        if country == "global":
            query = query.where(Project.country != "Uzbekistan")
        elif country:
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
            query = query.where(Project.published_at >= today_start(now))
        elif period in ("7d", "30d"):
            query = query.where(Project.published_at >= now - timedelta(days=7 if period == "7d" else 30))
        if year:
            query = query.where(
                Project.published_at >= datetime(year, 1, 1, tzinfo=timezone.utc),
                Project.published_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc),
            )
        order = {
            "date": Project.published_at,
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
            if project is None or project.publication_status != "PUBLISHED":
                raise HTTPException(404, "Loyiha topilmadi")
            result = serialize_project(project, detail=True)
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

    @app.get("/api/admin/review", dependencies=[Depends(require_admin)])
    def review_queue(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
        with factory() as session:
            query = select(Candidate).where(Candidate.status.in_(["pending", "review_required", "error"]))
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(query.order_by(Candidate.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
            return {"total": total, "items": [{
                "url": c.url, "title": (c.article or {}).get("title", ""), "source_id": c.source_id,
                "status": c.status, "reason": c.reason, "detector_result": c.detector_result,
                "creator": next((p.creator for pid in c.project_ids or [] if (p := session.get(Project, pid))), ""),
                "canonical_project": next((p.name for pid in c.project_ids or [] if (p := session.get(Project, pid))), ""),
                "primary_problem": next((p.problem_statement for pid in c.project_ids or [] if (p := session.get(Project, pid))), ""),
                "evidence": next(([{"url": e.url, "type": e.evidence_type, "quote": e.quote} for e in p.evidence_records[:5]] for pid in c.project_ids or [] if (p := session.get(Project, pid))), []),
                "confidence": next((p.confidence for pid in c.project_ids or [] if (p := session.get(Project, pid))), None),
                "review_decision": c.review_decision,
            } for c in rows]}

    @app.post("/api/admin/review/action", dependencies=[Depends(require_admin)])
    def review_action(url: str, action: Literal["ACCEPT", "REJECT", "KEEP_FOR_REVIEW"], reason: str = ""):
        allowed = {"not_project", "no_meaningful_problem", "minor_feature", "duplicate", "insufficient_evidence", "missing_creator", "signal_only", "irrelevant", "old_irrelevant_content", "other"}
        if action == "REJECT" and reason not in allowed:
            raise HTTPException(422, "Rad etish sababi kerak")
        with factory.begin() as session:
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
                               "project_candidates": sum(c.detector_result == "PROJECT_CANDIDATE" for c in rows),
                               "verified_projects": sum(projects[pid].visible for pid in linked),
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
