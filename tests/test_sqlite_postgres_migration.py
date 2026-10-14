"""Migration behavior is checked only against disposable SQLite databases."""

import sqlite3
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.config import Settings
from backend.app.db import (
    Base, Candidate, DailyStats, Project, RawDiscovery, RegistrySource, make_db,
    normalized_database_url,
)
from backend.app.sqlite_postgres_migration import (
    MigrationValidationError, copy_and_verify, diagnose_database, tables_to_copy,
)


def test_database_url_is_required():
    with pytest.raises(ValidationError, match="DATABASE_URL is required"):
        Settings(_env_file=None, database_url="")


def test_postgres_url_uses_psycopg_without_exposing_credentials():
    parsed = normalized_database_url("postgres://user:password@example.invalid:5432/catalog")
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.host == "example.invalid"


def test_tests_cannot_open_production_database(tmp_path):
    with pytest.raises(RuntimeError, match="isolated temporary SQLite"):
        make_db("postgresql+psycopg://user:password@example.invalid/catalog")
    with pytest.raises(RuntimeError, match="isolated temporary SQLite"):
        make_db("sqlite:////workspace/forbidden.sqlite3")
    engine, _ = make_db(f"sqlite:///{tmp_path / 'allowed.sqlite3'}")
    engine.dispose()


def test_postgres_schema_preserves_nullable_legacy_source_dates():
    ddl = str(CreateTable(RegistrySource.__table__).compile(dialect=postgresql.dialect()))
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "created_at TIMESTAMP WITH TIME ZONE" in ddl
    assert "CREATE TABLE sources" in ddl
    assert Candidate.__table__.c.reason.type.__class__.__name__ == "Text"
    assert RawDiscovery.__table__.c.failure_reason.type.__class__.__name__ == "Text"


def test_full_table_copy_is_idempotent_and_checks_values(tmp_path, capsys):
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    source_engine, factory = make_db(f"sqlite:///{source_path}")
    with factory.begin() as session:
        session.add(RegistrySource(id="sample", name="Sample", url="https://example.org/source"))
        session.add(DailyStats(day="2025-01-07", published_count=1))
        session.add(Project(
            id="b684f879-3f4c-498d-bc1a-b8c9f61180a6",
            name="Sample project", normalized_project_name="sample project",
            fingerprint="test-fingerprint", published_at=datetime(2025, 1, 7, tzinfo=timezone.utc),
            category="other", audience="individual", content={},
            catalog_section_override="boshqa", catalog_section_reason="manual review",
            publication_status="PUBLISHED", status_history=[{"value": "PUBLISHED"}],
        ))
    with source_engine.begin() as connection:
        connection.execute(text("UPDATE sources SET created_at=NULL WHERE id='sample'"))
    source_engine.dispose()

    target = create_engine(f"sqlite:///{target_path}")
    try:
        first = copy_and_verify(source_path, target)
        second = copy_and_verify(source_path, target)
        assert first == second
        assert {name for name, _, _ in first} == {table.name for table in tables_to_copy()}
        with target.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(Base.metadata.tables["sources"])) == 1
            assert connection.scalar(text("SELECT created_at FROM sources WHERE id='sample'")) is None
            project = connection.execute(text(
                "SELECT id,published_at,catalog_section_override,catalog_section_reason "
                "FROM projects WHERE name='Sample project'"
            )).one()
            assert project.id == "b684f879-3f4c-498d-bc1a-b8c9f61180a6"
            assert project.published_at.startswith("2025-01-07")
            assert (project.catalog_section_override, project.catalog_section_reason) == (
                "boshqa", "manual review",
            )

        with target.begin() as connection:
            connection.execute(text("UPDATE daily_stats SET published_count=2 WHERE day='2025-01-07'"))
        with pytest.raises(ValueError, match="rows or values differ"):
            copy_and_verify(source_path, target)
        assert "published_count (int->int)" in capsys.readouterr().out
        report = diagnose_database(source_path, target)
        assert report["daily_stats"]["changed"] == 1
        assert report["daily_stats"]["fields"] == {"published_count (int->int)": 1}
        with target.connect() as connection:
            assert connection.scalar(text("SELECT published_count FROM daily_stats")) == 2
        with sqlite3.connect(source_path) as connection:
            assert connection.execute("SELECT published_count FROM daily_stats").fetchone()[0] == 1
    finally:
        target.dispose()


def test_different_database_identity_is_not_overwritten(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    source, _ = make_db(f"sqlite:///{source_path}")
    source.dispose()
    target, factory = make_db(f"sqlite:///{tmp_path / 'new.sqlite3'}")
    with factory.begin() as session:
        session.add(DailyStats(day="2026-10-13", published_count=5))
    try:
        with pytest.raises(MigrationValidationError, match="identity differs"):
            copy_and_verify(source_path, target)
        report = diagnose_database(source_path, target)
        assert report["database_identity"]["changed"] == 1
        assert report["daily_stats"]["extra"] == 1
        with target.connect() as connection:
            assert connection.scalar(text("SELECT published_count FROM daily_stats")) == 5
    finally:
        target.dispose()


def test_diagnosis_does_not_open_live_postgres(tmp_path):
    target = create_engine("postgresql+psycopg://user:password@example.invalid/catalog")
    try:
        with pytest.raises(RuntimeError, match="isolated temporary SQLite"):
            diagnose_database(tmp_path / "source.sqlite3", target)
    finally:
        target.dispose()
