from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.app.analysis import ExtractiveAnalyzer
from backend.app.db import Candidate, Lease, Project, Run, now_utc
from backend.app.main import create_app
from backend.app.pipeline import Pipeline
from backend.app.scheduler import hourly_trigger, make_scheduler
from tests.conftest import FakeAnalyzer, FakeDiscovery, sample_analysis, sample_article


def test_complete_pipeline_and_repeat_idempotency(settings, factory):
    article = sample_article()
    pipeline = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer())
    result = pipeline.run()
    assert result["status"] == "completed"
    assert result["counts"]["new_projects"] == 1
    assert pipeline.run()["counts"]["new_projects"] == 0
    with factory() as session:
        assert len(session.scalars(select(Project)).all()) == 1
        assert session.get(Candidate, article.url).status == "published"
        assert session.scalars(select(Run)).first().finished_at is not None


def test_foreign_candidates_remain_pending_without_ai(settings, factory):
    article = sample_article()
    article.text = "В Узбекистане представили проект AgroKo‘mak для фермеров. Разработан прототип."
    pipeline = Pipeline(settings, factory, FakeDiscovery([article]), ExtractiveAnalyzer())
    result = pipeline.run()
    assert result["counts"]["pending"] == 1
    with factory() as session:
        assert not session.scalars(select(Project)).all()
        assert session.get(Candidate, article.url).status == "pending"


def test_reject_old_and_unknown_dates(settings, factory):
    old = sample_article()
    old.published_at = datetime(2021, 1, 1, tzinfo=timezone.utc)
    unknown = sample_article(url="https://news.example/unknown")
    unknown.published_at = None
    result = Pipeline(settings, factory, FakeDiscovery([old, unknown]), FakeAnalyzer()).run(archive=True)
    assert result["counts"]["rejected"] == 2
    assert result["counts"]["new_projects"] == 0


def test_lease_prevents_overlapping_runs_and_recovers(settings, factory):
    pipeline = Pipeline(settings, factory, FakeDiscovery([]), FakeAnalyzer())
    assert pipeline.acquire("first", now_utc())
    assert pipeline.run()["status"] == "busy"
    with factory.begin() as session:
        session.get(Lease, "pipeline").expires_at = now_utc() - timedelta(seconds=1)
    assert pipeline.run()["status"] == "completed"


def test_discovery_error_is_visible(settings, factory):
    discovery = FakeDiscovery([])
    discovery.discover = lambda *args: ([], [{"source": "Test", "code": "network_unavailable"}], 1)
    result = Pipeline(settings, factory, discovery, FakeAnalyzer()).run()
    assert result["status"] == "partial"
    assert result["errors"][0]["code"] == "network_unavailable"


def test_hourly_schedule_on_clock_boundary():
    now = datetime(2026, 10, 6, 9, 37, tzinfo=timezone.utc)
    next_run = hourly_trigger().get_next_fire_time(None, now)
    assert next_run.astimezone(timezone.utc) == datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)
    assert next_run.hour == 15


def test_scheduler_single_coalesced_job(settings, factory):
    scheduler = make_scheduler(settings, factory)
    job = scheduler.get_job("discovery")
    assert job.max_instances == 1
    assert job.coalesce is True


def test_api_filters_detail_status_and_not_found(settings, factory):
    article = sample_article()
    pipeline = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer())
    pipeline.run()
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        response = client.get(
            "/api/projects", params={"period": "all", "q": "Agro", "category": "agriculture", "min_rating": 1}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        detail = client.get("/api/projects/" + data["items"][0]["id"]).json()
        assert detail["content"]["facts"][0]["source_url"] == article.url
        assert detail["rating_components"]["practical"]["score"] == 1.5
        assert client.get("/api/projects", params={"q": "NoMatch", "period": "all"}).json()["total"] == 0
        assert client.get("/api/projects", params={"year": 2022, "period": "all"}).json()["total"] == 0
        assert (
            client.get("/api/projects", params={"audience": "business", "period": "all"}).json()["total"] == 0
        )
        assert client.get("/api/projects", params={"min_rating": 11}).status_code == 422
        assert client.get("/api/projects/missing").status_code == 404
        status = client.get("/api/admin/status", headers={"X-Admin-Key": "test-admin-key"}).json()
        assert status["last_run"]["counts"]["new_projects"] == 1
        assert status["next_run"] is None
        assert status["ai_enabled"] is False
        assert client.post("/api/run").status_code in (404, 405)
        assert "api_key" not in str(status)


def test_today_uses_publication_not_first_seen(settings, factory):
    article = sample_article()
    article.published_at = datetime(2022, 5, 1, tzinfo=timezone.utc)
    Pipeline(settings, factory, FakeDiscovery([])).persist(sample_analysis(article), [article], now_utc())
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects?period=today").json()["total"] == 0
        assert client.get("/api/projects?period=all&year=2022").json()["total"] == 1


def test_database_foreign_keys(settings, factory):
    from sqlalchemy.exc import IntegrityError
    from backend.app.db import Source
    import pytest

    with pytest.raises(IntegrityError), factory.begin() as session:
        session.add(
            Source(
                project_id="missing",
                url="https://example.com/no",
                publisher="Test",
                kind="news",
                published_at=now_utc(),
            )
        )


def test_archive_retries_an_article_outside_recent_window(settings, factory):
    article = sample_article()
    article.published_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    pipeline = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer())
    assert pipeline.run()["counts"]["rejected"] == 1
    assert pipeline.run(archive=True)["counts"]["new_projects"] == 1


def test_adding_ai_reanalyzes_extractive_project_without_duplicate(settings, factory):
    from pydantic import SecretStr

    article = sample_article()
    discovery = FakeDiscovery([article])
    result = Pipeline(settings, factory, discovery, ExtractiveAnalyzer()).run()
    assert result["counts"]["new_projects"] == 1
    settings.ai_api_key = SecretStr("test-only")
    result = Pipeline(settings, factory, discovery, FakeAnalyzer()).run()
    assert result["counts"]["new_projects"] == 0
    assert result["counts"]["duplicates"] == 1
    with factory() as session:
        projects = session.scalars(select(Project)).all()
        assert len(projects) == 1
        assert projects[0].content["analysis_mode"] == "ai"
        assert projects[0].creator == "Test University"


def test_ai_rejection_is_terminal_not_an_hourly_paid_retry(settings, factory):
    from backend.app.analysis import AnalysisError

    class RejectAnalyzer:
        def analyze(self, articles):
            raise AnalysisError("not_a_verified_uzbekistan_project")

    pipeline = Pipeline(settings, factory, FakeDiscovery([sample_article()]), RejectAnalyzer())
    result = pipeline.run()
    assert result["status"] == "completed"
    assert result["counts"]["rejected"] == 1
    assert pipeline.run()["counts"]["candidates"] == 0
