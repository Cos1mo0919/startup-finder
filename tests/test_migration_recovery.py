"""Recovery backup tests use temporary SQLite; rehearsal protocol uses a fake connection."""

import sqlite3
import math
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import Column, Float, MetaData, String, Table, create_engine, text
from sqlalchemy.dialects import postgresql

from backend.app.db import DailyStats, Project, make_db
from backend.app.migration_recovery import export_target, rehearse_transfer, temporary_table_sql
from backend.app.sqlite_postgres_migration import compare_table, configure_exact_float_reads, diagnose_database


def test_export_retains_existing_project_ids_dates_and_history(tmp_path, capsys):
    engine, factory = make_db(f"sqlite:///{tmp_path / 'current.sqlite3'}")
    backup_path = tmp_path / "before-recovery.sqlite3"
    try:
        with factory.begin() as session:
            session.add(DailyStats(day="2026-10-13", published_count=5))
            session.add(Project(
                id="existing-project", name="Existing", normalized_project_name="existing",
                fingerprint="existing", published_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
                category="other", audience="individual", content={"fact": "original"},
                publication_status="PUBLISHED", status_history=[{"value": "PUBLISHED"}],
            ))
        counts = export_target(engine, backup_path)
        assert len(counts) == 22
        assert counts["projects"] == 1
        report = diagnose_database(backup_path, engine)
        assert all(not any(row[key] for key in ("missing", "extra", "changed")) for row in report.values())
        capsys.readouterr()
        with sqlite3.connect(backup_path) as connection:
            row = connection.execute("SELECT id,published_at,status_history FROM projects").fetchone()
            assert row[0] == "existing-project"
            assert row[1].startswith("2026-10-13")
            assert "PUBLISHED" in row[2]
        original_backup = backup_path.read_bytes()
        with pytest.raises(FileExistsError):
            export_target(engine, backup_path)
        assert backup_path.read_bytes() == original_backup
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT published_count FROM daily_stats")) == 5
    finally:
        engine.dispose()


def test_recovery_tests_cannot_connect_to_production(tmp_path):
    engine = create_engine("postgresql+psycopg://user:secret@example.invalid/database")
    try:
        with pytest.raises(RuntimeError, match="isolated temporary SQLite"):
            export_target(engine, tmp_path / "backup.sqlite3")
        assert not (tmp_path / "backup.sqlite3").exists()
        with pytest.raises(RuntimeError, match="isolated temporary SQLite"):
            rehearse_transfer(tmp_path / "source.sqlite3", engine)
    finally:
        engine.dispose()


def test_export_refuses_to_silently_drop_unmodelled_columns(tmp_path):
    engine, _ = make_db(f"sqlite:///{tmp_path / 'current.sqlite3'}")
    destination = tmp_path / "backup.sqlite3"
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE projects ADD COLUMN extra_admin_note TEXT"))
        with pytest.raises(ValueError, match="Export source columns differ: projects"):
            export_target(engine, destination)
        assert not destination.exists()
        with engine.connect() as connection:
            assert "extra_admin_note" in [row[1] for row in connection.execute(text("PRAGMA table_info(projects)"))]
    finally:
        engine.dispose()


def test_rehearsal_rolls_back_temporary_ddl_after_insert_failure(tmp_path, monkeypatch):
    from backend.app import migration_recovery as recovery

    path = tmp_path / "source.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE items (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO items VALUES ('original')")
    table = Table("items", MetaData(), Column("id", String, primary_key=True))
    dialect = postgresql.dialect()
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.dialect = dialect
    connection.scalar.return_value = "UTC"
    transaction = connection.begin.return_value
    engine = SimpleNamespace(dialect=dialect, connect=lambda: connection)
    inspector = SimpleNamespace(
        default_schema_name="public", get_table_names=lambda **kwargs: ["items"],
        get_columns=lambda *args, **kwargs: [{"name": "id", "type": String()}],
    )
    # Only this fake engine bypasses the live-DB guard; no network connection exists.
    monkeypatch.setattr(recovery, "validate_test_target", lambda _: None)
    monkeypatch.setattr(recovery, "validate_source", lambda *_: None)
    monkeypatch.setattr(recovery, "tables_to_copy", lambda: [table])
    monkeypatch.setattr(recovery, "inspect", lambda _: inspector)
    monkeypatch.setattr(recovery, "_insert_batch", Mock(side_effect=RuntimeError("simulated failure")))
    with pytest.raises(RuntimeError, match="simulated failure"):
        rehearse_transfer(path, engine)
    transaction.rollback.assert_called_once()
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert any(statement.startswith("CREATE TEMP TABLE") for statement in statements)
    assert "SET LOCAL search_path TO pg_temp, pg_catalog" in statements
    assert statements.index("SET LOCAL extra_float_digits = 3") < next(
        index for index, statement in enumerate(statements) if statement.startswith("CREATE TEMP TABLE")
    )
    assert not any(statement.startswith(("DELETE", "UPDATE", "DROP", "ALTER")) for statement in statements)


def test_temporary_sql_quotes_schema_and_cannot_drop_production_tables():
    sql = temporary_table_sql(postgresql.dialect().identifier_preparer, "public", "projects")
    assert sql == 'CREATE TEMP TABLE "projects" (LIKE public."projects" INCLUDING ALL) ON COMMIT DROP'


def test_float_transport_setting_is_transaction_local_and_sqlite_unchanged():
    connection = Mock(dialect=postgresql.dialect())
    connection.scalar.return_value = "0"
    assert configure_exact_float_reads(connection) == "0"
    assert str(connection.execute.call_args.args[0]) == "SET LOCAL extra_float_digits = 3"
    sqlite_connection = Mock(dialect=SimpleNamespace(name="sqlite"))
    assert configure_exact_float_reads(sqlite_connection) is None
    sqlite_connection.execute.assert_not_called()


def test_float_verification_rejects_even_one_ulp_loss(tmp_path):
    # Model a text-protocol read losing a single binary64 unit. Verification
    # must not turn the reported migration failure into an accepted tolerance.
    source_path = tmp_path / "float-source.sqlite3"
    table = Table("items", MetaData(), Column("id", String, primary_key=True), Column("latency", Float))
    value = 1234567.123456789
    with sqlite3.connect(source_path) as source:
        source.row_factory = sqlite3.Row
        source.execute("CREATE TABLE items (id TEXT PRIMARY KEY, latency REAL)")
        source.execute("INSERT INTO items VALUES (?, ?)", ("provider", value))
        target = Mock()
        target.execute.return_value.mappings.return_value = [{"id": "provider", "latency": math.nextafter(value, math.inf)}]
        difference = compare_table(source, target, table)
        assert difference["changed"] == 1
        assert difference["numeric_max_abs_delta"]["latency"] == math.ulp(value)
        target.execute.return_value.mappings.return_value = [{"id": "provider", "latency": value}]
        assert compare_table(source, target, table)["changed"] == 0
