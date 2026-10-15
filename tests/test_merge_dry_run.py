"""Merge planning never opens DATABASE_URL or changes either input snapshot."""

import hashlib
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.app.db import Candidate, Project, Run, Source, make_db
from backend.app.merge_dry_run import digest_snapshot, plan_merge, read_snapshot, simulate
from backend.app.sqlite_postgres_migration import MigrationValidationError


def project(identifier, name):
    return Project(id=identifier, name=name, normalized_project_name=name.lower(),
                   fingerprint=identifier, category="other", audience="business", content={},
                   published_at=datetime(2025, 1, 7, tzinfo=timezone.utc),
                   publication_status="PUBLISHED", visible=True)


def snapshots(tmp_path):
    paths = [tmp_path / "source.sqlite3", tmp_path / "target.sqlite3"]
    for side, path in zip(("source", "target"), paths):
        engine, factory = make_db(f"sqlite:///{path}")
        with factory.begin() as session:
            session.add(project(side, "Screenspell"))
            session.add(Run(id=1, status=side))
            session.flush()
            session.add(Source(id=1, project_id=side, url="https://example.org/screenspell",
                               publisher=side, kind="official", published_at=datetime(2025, 1, 7, tzinfo=timezone.utc)))
            session.add(Candidate(url="https://example.org/common", article={"side": side},
                                  project_ids=[side], last_run_id=1, status="published"))
            if side == "source":
                session.add(Candidate(url="https://example.org/new", article={}, project_ids=[side], last_run_id=1))
            else:
                for index in range(4):
                    session.add(project(f"protected-{index}", f"Protected {index}"))
        engine.dispose()
    return paths


def test_dry_run_protects_five_projects_ids_dates_and_all_target_rows(tmp_path, monkeypatch):
    source_path, target_path = snapshots(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://never-connect.invalid/production")
    original_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (source_path, target_path)]
    source, target = read_snapshot(source_path), read_snapshot(target_path)
    report, additions = plan_merge(source, target)
    assert len(report["protected_projects"]) == 5
    assert len(report["project_duplicates"]) == 1
    assert report["tables"]["schema_migrations"]["added"] == 0
    assert report["tables"]["runs"]["remapped_integer_ids"] == 1
    assert additions["runs"][0]["id"] == 2
    candidate = additions["candidates"][0]
    assert candidate["last_run_id"] == 2
    assert candidate["project_ids"] == ["target"]
    duplicate = additions["projects"][0]
    assert duplicate["id"] == "source"
    assert duplicate["published_at"] == source["projects"][0]["published_at"]
    assert duplicate["publication_status"] == "DUPLICATE"
    assert duplicate["visible"] is False
    assert additions["project_sources"] == []
    result = simulate(target_path, target, report, additions)
    assert result["transaction_rolled_back"] and result["all_target_rows_unchanged"]
    assert original_hashes == [hashlib.sha256(path.read_bytes()).hexdigest() for path in (source_path, target_path)]
    assert plan_merge(source, target)[0] == report  # reproducible plan


def test_name_only_is_blocker_and_shared_cohort_does_not_merge_other_projects(tmp_path):
    paths = snapshots(tmp_path)
    source, target = map(read_snapshot, paths)
    source["projects"][0]["name"] = "KotibAI"
    target["projects"][0]["name"] = "Kotib AI"
    source["project_sources"][0]["url"] = "https://example.org/different"
    report, _ = plan_merge(source, target)
    assert len(report["blockers"]) == 1
    assert not report["ready_for_live_merge"]
    assert not report["project_duplicates"]
    source["projects"][0]["name"] = "A different product"
    source["project_sources"][0]["url"] = target["project_sources"][0]["url"]
    assert not plan_merge(source, target)[0]["project_duplicates"]


@pytest.mark.parametrize("failure", ["count", "value", "fk"])
def test_simulation_aborts_on_any_mismatch_and_keeps_target_intact(tmp_path, failure):
    source_path, target_path = snapshots(tmp_path)
    source, target = read_snapshot(source_path), read_snapshot(target_path)
    report, additions = plan_merge(source, target)
    original = digest_snapshot(target)
    if failure == "count":
        report["tables"]["projects"]["target_after"] += 1
    elif failure == "value":
        target = deepcopy(target)
        target["projects"][0]["name"] = "tampered expected value"
    else:
        additions["candidates"][0]["source_id"] = "missing-source"
    with pytest.raises(Exception, match="mismatch|FOREIGN KEY"):
        simulate(target_path, target, report, additions)
    assert digest_snapshot(read_snapshot(target_path)) == original


def test_simulation_rejects_stale_snapshot_even_if_count_same(tmp_path):
    source_path, target_path = snapshots(tmp_path)
    source, target = read_snapshot(source_path), read_snapshot(target_path)
    report, additions = plan_merge(source, target)
    engine, _ = make_db(f"sqlite:///{target_path}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE projects SET name='New admin edit' WHERE id='target'"))
    engine.dispose()
    with pytest.raises(MigrationValidationError, match="value mismatch"):
        simulate(target_path, target, report, additions)
    assert next(row for row in read_snapshot(target_path)["projects"] if row["id"] == "target")["name"] == "New admin edit"


def test_explicit_decision_resolves_only_named_conflict(tmp_path):
    source, target = map(read_snapshot, snapshots(tmp_path))
    source["project_sources"][0]["url"] = "https://example.org/another"
    assert plan_merge(source, target)[0]["blockers"]
    report, additions = plan_merge(source, target, {"source": {"action": "merge", "target_id": "target"}})
    assert not report["blockers"]
    assert additions["projects"][0]["publication_status"] == "DUPLICATE"
    report, additions = plan_merge(source, target, {"source": {"action": "keep_separate"}})
    assert not report["blockers"]
    assert additions["projects"][0]["publication_status"] == "PUBLISHED"
    with pytest.raises(MigrationValidationError):
        plan_merge(source, target, {"unrelated": {"action": "keep_separate"}})


def test_executor_commit_protects_existing_and_second_run_is_idempotent(tmp_path):
    from backend.app.merge_execute import execute_merge
    source_path, target_path = snapshots(tmp_path)
    source, target = read_snapshot(source_path), read_snapshot(target_path)
    report, additions = plan_merge(source, target)
    report["simulation"] = simulate(target_path, target, report, additions)
    # Distinct immutable backup and live disposable SQLite test database.
    live_path = tmp_path / "live.sqlite3"
    live_path.write_bytes(target_path.read_bytes())
    engine, _ = make_db(f"sqlite:///{live_path}")
    try:
        with pytest.raises(MigrationValidationError, match="Stop backend"):
            execute_merge(engine, source_path, target_path, report)
        result = execute_merge(engine, source_path, target_path, report, writers_stopped=True)
        assert result["status"] == "rolled_back"
        assert digest_snapshot(read_snapshot(live_path)) == report["target_digest"]
        result = execute_merge(engine, source_path, target_path, report, apply=True, writers_stopped=True)
        assert result["status"] == "committed"
        assert result["table_counts"]["projects"] == 6
        assert execute_merge(engine, source_path, target_path, report, apply=True,
                             writers_stopped=True)["status"] == "already_applied"
    finally:
        engine.dispose()


def test_executor_value_failure_rolls_back_all_inserts(tmp_path, monkeypatch):
    from backend.app import merge_execute
    source_path, target_path = snapshots(tmp_path)
    report, additions = plan_merge(read_snapshot(source_path), read_snapshot(target_path))
    report["simulation"] = {"passed": True}
    engine, _ = make_db(f"sqlite:///{target_path}")
    def fail(*_):
        raise MigrationValidationError("Injected count mismatch")
    monkeypatch.setattr(merge_execute, "verify_merge", fail)
    try:
        with pytest.raises(MigrationValidationError, match="count mismatch"):
            merge_execute.execute_merge(engine, source_path, target_path, report, apply=True, writers_stopped=True)
        assert digest_snapshot(read_snapshot(target_path)) == report["target_digest"]
    finally:
        engine.dispose()


def test_executor_refuses_changed_database_and_unresolved_conflicts(tmp_path):
    from backend.app.merge_execute import execute_merge
    source_path, target_path = snapshots(tmp_path)
    source, target = read_snapshot(source_path), read_snapshot(target_path)
    report, _ = plan_merge(source, target)
    report["simulation"] = {"passed": True}
    live_path = tmp_path / "live.sqlite3"
    live_path.write_bytes(target_path.read_bytes())
    engine, _ = make_db(f"sqlite:///{live_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE projects SET name='Admin edit' WHERE id='target'"))
        with pytest.raises(MigrationValidationError, match="changed since"):
            execute_merge(engine, source_path, target_path, report, apply=True, writers_stopped=True)
    finally:
        engine.dispose()


def test_apply_cli_requires_restore_proof_before_any_connection(tmp_path, monkeypatch, capsys):
    from backend.app import merge_execute
    def never_connect(*_, **__):
        raise AssertionError("must not connect")
    monkeypatch.setattr(merge_execute, "create_engine", never_connect)
    assert merge_execute.main(["--source", "source.sqlite3", "--target-backup", "backup.sqlite3",
                               "--approved-report", "approved.json", "--writers-stopped", "--apply"]) == 1
    assert "requires --restore-report" in capsys.readouterr().err


def test_sequence_restart_uses_transactional_ddl_not_setval():
    from unittest.mock import Mock
    from sqlalchemy import Column, Integer, MetaData, Table
    from sqlalchemy.dialects import postgresql
    from backend.app import merge_execute
    from unittest.mock import patch
    table = Table("items", MetaData(), Column("id", Integer, primary_key=True))
    connection = Mock(dialect=postgresql.dialect())
    connection.scalar.side_effect = ["public.items_id_seq", 99]
    connection.execute.return_value.one.return_value = ("public", "items_id_seq")
    with patch.object(merge_execute, "tables_to_copy", return_value=[table]):
        merge_execute.restart_sequences(connection)
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert 'ALTER SEQUENCE "public"."items_id_seq" RESTART WITH 100' in statements
    assert all("setval" not in statement.lower() for statement in statements)
