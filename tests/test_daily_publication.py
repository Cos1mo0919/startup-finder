from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_store import save_catalog_result
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.catalog_admin import catalog_action
from backend.app.daily import DailyLimitReached, publication_summary, reserve_publication, today_stats
from backend.app.db import Candidate, DailyStats, DatabaseIdentity, Project, RegistrySource, make_db, now_utc
from tests.conftest import FakeDiscovery, sample_article


def test_daily_limit_and_tashkent_rollover(settings, factory):
    settings = settings.model_copy(update={"daily_publish_limit": 2, "daily_uz_limit": 1})
    before_midnight = datetime(2026, 10, 11, 18, 59, tzinfo=timezone.utc)
    after_midnight = before_midnight + timedelta(minutes=2)
    with factory.begin() as session:
        reserve_publication(session, settings, "Global", before_midnight)
        reserve_publication(session, settings, "GitHub", before_midnight)
        with pytest.raises(DailyLimitReached, match="daily_publish_limit_reached"):
            reserve_publication(session, settings, "Uzbekistan", before_midnight)
        reserve_publication(session, settings, "Uzbekistan", after_midnight)
    with factory() as session:
        assert today_stats(session, settings, before_midnight)["published"] == 2
        assert today_stats(session, settings, after_midnight)["published"] == 1
        assert session.scalars(select(DailyStats)).all()
        assert publication_summary(session, settings, after_midnight)["week"] == 3


def test_boshqa_publication_uses_a_real_daily_slot(settings, factory):
    settings = settings.model_copy(update={"daily_publish_limit": 1, "daily_uz_limit": 0})
    when = datetime(2026, 10, 12, 8, tzinfo=timezone.utc)
    with factory.begin() as session:
        reserve_publication(session, settings, "Boshqa", when)
        with pytest.raises(DailyLimitReached):
            reserve_publication(session, settings, "Global", when)
    with factory() as session:
        stats = today_stats(session, settings, when)
        assert stats["published"] == stats["boshqa"] == 1


def test_nonlocal_reservation_released_after_local_queue_exhausted(settings, factory):
    settings = settings.model_copy(update={"daily_publish_limit": 3, "daily_uz_limit": 1})
    when = datetime(2026, 10, 11, 6, tzinfo=timezone.utc)
    with factory.begin() as session:
        session.add(RegistrySource(id="local", name="Local", url="https://local.example/",
                                   country="Uzbekistan", enabled=True))
        session.flush()
        session.add(Candidate(url="https://local.example/tool", article={}, source_id="local", status="queued"))
    with factory.begin() as session:
        reserve_publication(session, settings, "Global", when)
        reserve_publication(session, settings, "GitHub", when)
        with pytest.raises(DailyLimitReached, match="local_reservation_active"):
            reserve_publication(session, settings, "Global", when)
        session.get(Candidate, "https://local.example/tool").status = "rejected"
        session.flush()
        reserve_publication(session, settings, "Global", when)
        assert today_stats(session, settings, when)["published"] == 3


def test_catalog_publication_reserves_only_new_transitions(settings, factory):
    settings = settings.model_copy(update={"daily_publish_limit": 1, "daily_uz_limit": 0})
    when = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    def publish(name):
        article = sample_article(name, f"https://example.com/{name.lower()}")
        entry = CatalogEntry(name=name, confidence=0.9,
            description_uz=f"{name} fermerlarga sug‘orish xarajatlarini kuzatish va ishlarni rejalash imkonini beradi")
        with factory.begin() as session:
            return save_catalog_result(session, article, CatalogResult("PROJECT", 0.9, (entry,)),
                                       when, settings)

    assert publish("Alpha")["auto_published"] == 1
    assert publish("Alpha")["auto_published"] == 0
    with pytest.raises(DailyLimitReached):
        publish("Beta")
    with factory() as session:
        assert session.scalar(select(Project).where(Project.name == "Beta")) is None
        assert today_stats(session, settings, when)["published"] == 1


def test_database_identity_survives_reopen(settings, factory):
    with factory() as session:
        original = session.get(DatabaseIdentity, "primary").instance_uuid
    engine, reopened = make_db(settings.database_url)
    with reopened() as session:
        assert session.get(DatabaseIdentity, "primary").instance_uuid == original
    engine.dispose()


def test_pipeline_stops_at_daily_limit_and_preserves_queue(settings, factory):
    pages = [sample_article(name, f"https://example.com/{name.lower()}")
             for name in ("Alpha", "Beta", "Gamma")]
    class Classifier:
        def classify(self, article):
            name = article.title.split("”")[0].lstrip("“")
            return CatalogResult("PROJECT", 0.9, (CatalogEntry(name=name, confidence=0.9,
                description_uz=f"{name} fermerlarga sug‘orish sarfini kuzatish va ishlarni rejalash imkonini beradi"),),
                analysis_method="llm")

    settings = settings.model_copy(update={"daily_publish_limit": 1, "daily_uz_limit": 0,
                                   "ai_api_key": SecretStr("test-key"), "max_candidates": 3})
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery(pages), classifier=Classifier())
    result = pipeline.run(reanalyze=False)
    assert result["counts"]["auto_published"] == 1
    assert result["details"]["stop_reason"] == "daily_publish_limit_reached"
    assert result["details"]["remaining_queue"] == 2
    assert pipeline.run(discover=False, reanalyze=False)["counts"]["candidates"] == 0
    with factory() as session:
        assert session.scalar(select(DailyStats.published_count)) == 1
        assert session.scalar(select(Project.name)) == "Alpha"
    pipeline.close()


def test_admin_restore_does_not_count_an_old_project_as_a_new_publication(settings, factory):
    settings = settings.model_copy(update={"daily_publish_limit": 1, "daily_uz_limit": 0})
    when = now_utc()
    article = sample_article("Alpha", "https://example.com/alpha")
    entry = CatalogEntry(name="Alpha", confidence=0.9,
        description_uz="Alpha fermerlarga sug‘orish sarfini kuzatish va ishlarni rejalash imkonini beradi")
    with factory.begin() as session:
        save_catalog_result(session, article, CatalogResult("PROJECT", 0.9, (entry,)), when, settings)
        project = session.scalar(select(Project))
        project.publication_status = "REVIEW_REQUIRED"
        project.visible = False
        project_id = project.id
    with factory.begin() as session:
        catalog_action(session, project_id, "PUBLISH", settings=settings)
    with factory() as session:
        assert session.get(Project, project_id).publication_status == "PUBLISHED"
        assert session.scalar(select(DailyStats.published_count)) == 1


def test_scheduled_drain_skips_after_cap(settings, factory):
    from backend.app.scheduler import drain_once
    settings = settings.model_copy(update={"daily_publish_limit": 1, "daily_uz_limit": 0})
    with factory.begin() as session:
        reserve_publication(session, settings, "Global")
    result = drain_once(settings, factory)
    assert result["status"] == "daily_limit_reached"
