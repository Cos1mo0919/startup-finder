from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_store import save_catalog_result
from backend.app.db import Project
from backend.app.geography import project_scope
from backend.app.main import create_app
from tests.conftest import sample_article


def _publish(factory, name, url, published, country=""):
    article = sample_article(name, url)
    article.published_at = published
    entry = CatalogEntry(name=name, country=country or None, confidence=0.9,
                         description_uz=f"{name} talabalar uchun hujjatlarni tartiblash va topshiriqlarni boshqarish imkonini beradi")
    with factory.begin() as session:
        save_catalog_result(session, article, CatalogResult("PROJECT", 0.9, (entry,)))
        project = session.scalar(select(Project).where(Project.name == name))
        return project.id


def test_boshqa_requires_published_project_and_admin_assignment(settings, factory):
    old = _publish(factory, "UnknownTool", "https://unknown.example/tool",
                   datetime(2025, 6, 1, tzinfo=timezone.utc))
    with factory() as session:
        project = session.get(Project, old)
        assert project_scope(project) == "Boshqa"
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/admin/catalog?section=Boshqa", headers={"X-Admin-Key": "test-admin-key"}).json()["total"] == 1
        assert client.get("/api/projects?country=boshqa").json()["total"] == 1
        assert client.get("/api/projects?archive=true&year=2025").json()["total"] == 1
        assert client.get("/api/projects?country=global").json()["total"] == 0
        assert client.post(f"/api/admin/projects/{old}/section?section=Global&reason=Official%20company%20review").status_code == 401
        response = client.post(f"/api/admin/projects/{old}/section?section=Global&reason=Official%20company%20review",
                               headers={"X-Admin-Key": "test-admin-key"})
        assert response.status_code == 200
        assert client.get("/api/projects?country=boshqa").json()["total"] == 0
        assert client.get("/api/projects?country=global").json()["total"] == 1
        assert client.get("/api/projects?archive=true&year=2025").json()["total"] == 1
    with factory() as session:
        project = session.get(Project, old)
        assert project.attribute_history[-1]["value"] == "Global"
        assert project.published_at.year == 2025


def test_home_uses_publication_day_then_yesterday_then_three_days(settings, factory, monkeypatch):
    fixed = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("backend.app.main.now_utc", lambda: fixed)
    old = _publish(factory, "OldTool", "https://unknown.example/old",
                   datetime(2025, 7, 1, tzinfo=timezone.utc))
    recent = _publish(factory, "RecentTool", "https://unknown.example/recent",
                      fixed - timedelta(days=2))
    with TestClient(create_app(settings)) as client:
        home = client.get("/api/catalog/home").json()
        assert home["fresh_period"] == "three_days"
        assert [item["name"] for item in home["top"]] == ["RecentTool"]
        assert client.get("/api/projects?archive=true").json()["total"] == 1
        with factory.begin() as session:
            session.get(Project, recent).published_at = fixed - timedelta(days=1)
        assert client.get("/api/catalog/home").json()["fresh_period"] == "yesterday"
        with factory.begin() as session:
            session.get(Project, recent).published_at = fixed
        assert client.get("/api/catalog/home").json()["fresh_period"] == "today"
        with factory.begin() as session:
            session.get(Project, recent).published_at = fixed - timedelta(days=4)
        assert client.get("/api/catalog/home").json()["top"] == []
        assert client.get("/api/catalog/home").json()["fresh_period"] == "empty"
        assert client.get("/api/projects?archive=true&year=2025").json()["items"][0]["id"] == old


def test_facets_and_year_filters_do_not_use_discovered_at(settings, factory):
    _publish(factory, "OldTool", "https://unknown.example/old",
             datetime(2025, 11, 30, tzinfo=timezone.utc))
    _publish(factory, "NewTool", "https://github.com/example/newtool",
             datetime(2026, 10, 10, tzinfo=timezone.utc))
    with TestClient(create_app(settings)) as client:
        facets = client.get("/api/catalog/facets").json()
        assert facets["total"] == 2
        assert facets["years"] == {"2025": 1, "2026": 1}
        assert facets["sections"]["Boshqa"] == 1
        assert facets["sections"]["GitHub"] == 1
        assert client.get("/api/projects?year=2025").json()["total"] == 1
        assert client.get("/api/projects?year=2026&country=github").json()["total"] == 1
