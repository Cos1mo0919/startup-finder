"""Real PostgreSQL regression. Ignores DATABASE_URL; creates/drops only its UUID test DB."""

import os
from uuid import uuid4
from urllib.parse import urlsplit
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.db import Base, Candidate, Lease, Project, RawDiscovery, Run
from backend.app.free_daily import run_daily
from backend.app.llm_service import LLMAnalysis
from tests.conftest import FakeDiscovery, sample_article


@pytest.fixture
def postgres_factory():
    # Deliberately no URL env override and no make_db guard relaxation. CI supplies
    # only a localhost service port; production DATABASE_URL is never inspected.
    value = os.environ.get("IZLANISH_TEST_PG_PORT")
    if not value:
        pytest.skip("Disposable PostgreSQL unavailable: set IZLANISH_TEST_PG_PORT; Cloud provisioning is network-blocked. Production DATABASE_URL is never used.")
    if not value.isdigit() or not 1024 <= int(value) <= 65535:
        raise RuntimeError("Invalid disposable PostgreSQL port")
    database = "izlanish_test_" + uuid4().hex
    from psycopg import sql

    admin = create_engine(
        f"postgresql+psycopg://postgres:izlanish-test-only@127.0.0.1:{int(value)}/postgres",
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.connection.driver_connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
            )
        created = True
        engine = create_engine(admin.url.set(database=database), connect_args={"connect_timeout": 3})
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory.begin() as session:
            session.add(
                Lease(name="pipeline", owner="", expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
            )
        yield factory
    finally:
        if engine:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.connection.driver_connection.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
                )
        admin.dispose()


class OfflineClassifier:
    available = operational = True
    last_attempt_count = 0

    def analyze_source(self, article):
        number = int(urlsplit(article.url).path.rsplit("/", 1)[1])
        if number < 3:
            result = CatalogResult("NOT_PROJECT", 0.95, (), "Market overview")
        elif number == 3:
            result = CatalogResult("NOT_PROJECT", 0.6, (), "Ambiguous source")
        else:
            entry = CatalogEntry(
                name="FixtureCloud",
                confidence=0.95,
                country="Uzbekistan",
                description_uz="FixtureCloud talabalar arizalarini bir joyda qabul qiladi va kundalik ishni tezlashtiradi",
            )
            result = CatalogResult("PROJECT", 0.95, (entry,))
        return LLMAnalysis(result, "gemini", "offline-fixture", 1)

    def status(self):
        return []


@pytest.mark.parametrize("existing", [0, 5])
def test_daily_trial_postgres_reject_review_then_publish(settings, postgres_factory, existing):
    factory = postgres_factory
    urls = []
    with factory.begin() as session:
        for index in range(existing):
            session.add(
                Project(
                    id=str(uuid4()),
                    name=f"Legacy-{index}",
                    normalized_project_name=f"legacy {index}",
                    fingerprint=str(index),
                    published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                    category="other",
                    audience="unknown",
                    content={"summary_uz": "Historical fixture"},
                    publication_status="PUBLISHED",
                    visible=True,
                )
            )
        session.flush()
        baseline = list(session.execute(select(Project.id, Project.published_at)))
        for index in range(5):
            article = sample_article(name="FixtureCloud", url=f"https://fixture.example/{index}?q=100%25")
            urls.append(article.url)
            session.add(Candidate(url=article.url, article=article.model_dump(mode="json"), status="queued"))

    def pipeline(config, factory):
        return CatalogPipeline(config, factory, FakeDiscovery([]), llm_service=OfflineClassifier())

    settings = settings.model_copy(update={"llm_batch_delay_seconds": 0})
    result = run_daily(settings, factory, trial=True, pipeline_factory=pipeline)
    with factory() as session:
        outer = session.get(Run, result["run_id"])
        assert result["status"] == "completed", outer.errors
        assert result["counts"]["published"] == 1, outer.errors
        assert result["counts"]["rejected"] == 3
        project = session.scalar(select(Project).where(Project.name == "FixtureCloud"))
        assert project.publication_status == "PUBLISHED" and project.visible
        assert project.sources and project.evidence_records
        published = session.get(Candidate, urls[4])
        assert published.status == "published" and published.entity_type == "PROJECT"
        assert published.project_ids == [project.id]
        assert session.scalar(select(func.count()).select_from(RawDiscovery)) == 5
        assert (
            session.scalar(
                select(RawDiscovery).where(RawDiscovery.source_url == urls[4])
            ).canonical_project_id
            == project.id
        )
        assert dict(
            session.execute(
                select(Project.id, Project.published_at).where(Project.id.in_([row.id for row in baseline]))
            ).all()
        ) == dict(baseline)
