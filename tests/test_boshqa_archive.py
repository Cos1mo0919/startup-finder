import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_store import save_catalog_result
from backend.app.db import Project
from backend.app.geography import project_scope
from backend.app.main import create_app
from tests.conftest import sample_article


def _publish(factory, name, url, published, country="", when=None):
    article = sample_article(name, url)
    article.published_at = published
    entry = CatalogEntry(name=name, country=country or None, confidence=0.9,
                         description_uz=f"{name} talabalar uchun hujjatlarni tartiblash va topshiriqlarni boshqarish imkonini beradi")
    with factory.begin() as session:
        save_catalog_result(session, article, CatalogResult("PROJECT", 0.9, (entry,)), when=when)
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


def _redate(factory, project_id, when):
    with factory.begin() as session:
        session.get(Project, project_id).published_at = when


def test_home_uses_card_date_today_then_yesterday_then_latest_week_day(settings, factory, monkeypatch):
    # 2026-10-12 17:00 Tashkent. The card date (article date, or discovery date when unknown) decides.
    fixed = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("backend.app.main.now_utc", lambda: fixed)
    old = _publish(factory, "OldTool", "https://unknown.example/old",
                   datetime(2023, 7, 1, tzinfo=timezone.utc), when=fixed - timedelta(hours=2))
    recent = _publish(factory, "RecentTool", "https://unknown.example/recent", fixed - timedelta(hours=1))
    with TestClient(create_app(settings)) as client:
        home = client.get("/api/catalog/home").json()
        assert home["fresh_period"] == "today" and home["fresh_day"] == "2026-10-12"
        # The 2023 article found today is not a "today" project.
        assert [item["name"] for item in home["top"]] == ["RecentTool"]
        _redate(factory, recent, datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc))  # yesterday 23:00 Tashkent
        home = client.get("/api/catalog/home").json()
        assert home["fresh_period"] == "yesterday" and [item["name"] for item in home["top"]] == ["RecentTool"]
        _redate(factory, recent, fixed - timedelta(days=3))
        home = client.get("/api/catalog/home").json()
        assert home["fresh_period"] == "latest" and home["fresh_day"] == "2026-10-09"
        assert [item["name"] for item in home["top"]] == ["RecentTool"]
        _redate(factory, recent, fixed - timedelta(days=9))  # Older than a week: archive only.
        home = client.get("/api/catalog/home").json()
        assert home["fresh_period"] == "empty" and home["top"] == []
        assert client.get("/api/projects?archive=true&year=2023").json()["items"][0]["id"] == old


@pytest.mark.parametrize("now,period,start,end", [
    # Monday–Wednesday (Tashkent) show the previous Monday–Sunday week.
    (datetime(2026, 10, 19, 4, tzinfo=timezone.utc), "last_week", "2026-10-12", "2026-10-18"),   # Mon 09:00
    (datetime(2026, 10, 21, 18, 59, tzinfo=timezone.utc), "last_week", "2026-10-12", "2026-10-18"),  # Wed 23:59
    # From Thursday the current week.
    (datetime(2026, 10, 21, 19, 0, tzinfo=timezone.utc), "this_week", "2026-10-19", "2026-10-25"),  # Thu 00:00
    (datetime(2026, 10, 25, 18, tzinfo=timezone.utc), "this_week", "2026-10-19", "2026-10-25"),   # Sun 23:00
    # Sunday 20:00 UTC is already Monday in Tashkent.
    (datetime(2026, 10, 25, 20, tzinfo=timezone.utc), "last_week", "2026-10-19", "2026-10-25"),
])
def test_recent_filter_uses_card_date_and_week_rule(settings, factory, monkeypatch, now, period, start, end):
    monkeypatch.setattr("backend.app.main.now_utc", lambda: now)
    week_start = datetime.fromisoformat(start).replace(tzinfo=timezone(timedelta(hours=5)))
    inside = _publish(factory, "InsideTool", "https://unknown.example/inside",
                      (week_start + timedelta(days=1, hours=20)).astimezone(timezone.utc))
    _publish(factory, "BeforeTool", "https://unknown.example/before",
             (week_start - timedelta(minutes=1)).astimezone(timezone.utc))
    _publish(factory, "AfterTool", "https://unknown.example/after",
             (week_start + timedelta(days=7)).astimezone(timezone.utc))
    # Found inside the week but written in 2023: not recent.
    _publish(factory, "OldArticleTool", "https://unknown.example/old-article",
             datetime(2023, 10, 25, tzinfo=timezone.utc), when=(week_start + timedelta(days=2)).astimezone(timezone.utc))
    with TestClient(create_app(settings)) as client:
        listing = client.get("/api/projects?period=recent").json()
        facets = client.get("/api/catalog/facets").json()
        assert [item["id"] for item in listing["items"]] == [inside]
        assert facets["recent"] == {"period": period, "start": start, "end": end, "total": 1}
        # Combines with the other filters instead of replacing them.
        assert client.get("/api/projects?period=recent&q=Inside").json()["total"] == 1
        assert client.get("/api/projects?period=recent&q=Before").json()["total"] == 0


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
