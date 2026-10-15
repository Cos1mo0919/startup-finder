"""Explicit, guarded PostgreSQL merge. Default execution always rolls back."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Integer, create_engine, func, inspect, select, text

from .config import Settings
from .db import normalized_database_url
from .merge_dry_run import digest_snapshot, plan_merge, read_snapshot
from .sqlite_postgres_migration import (
    MigrationValidationError, configure_exact_float_reads, tables_to_copy, validate_test_target,
)


def database_rows(connection):
    return {table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
            for table in tables_to_copy()}


def verify_merge(connection, expected):
    actual = database_rows(connection)
    for table in tables_to_copy():
        if len(actual[table.name]) != len(expected[table.name]):
            raise MigrationValidationError(f"Merge count mismatch: {table.name}")
    if digest_snapshot(actual) != digest_snapshot(expected):
        raise MigrationValidationError("Merge values differ; including protected target rows")
    return {name: len(rows) for name, rows in actual.items()}


def restart_sequences(connection):
    """ALTER SEQUENCE RESTART rolls back; setval would not."""
    if connection.dialect.name != "postgresql":
        return
    for table in tables_to_copy():
        if table.name == "schema_migrations":
            continue
        for col in table.primary_key.columns:
            if not isinstance(col.type, Integer):
                continue
            sequence = connection.scalar(text("SELECT pg_get_serial_sequence(:table, :col)"),
                                         {"table": table.name, "col": col.name})
            if not sequence:
                continue
            parts = connection.execute(text("SELECT n.nspname, c.relname FROM pg_class c "
                                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                                            "WHERE c.oid=CAST(:sequence AS regclass)"),
                                       {"sequence": sequence}).one()
            quote = connection.dialect.identifier_preparer.quote_identifier
            identifier = ".".join(quote(part) for part in parts)
            next_id = (connection.scalar(select(func.max(col))) or 0) + 1
            connection.execute(text(f"ALTER SEQUENCE {identifier} RESTART WITH {int(next_id)}"))


def execute_merge(engine, source_path, backup_path, approved, *, apply=False, writers_stopped=False):
    validate_test_target(engine)
    if not writers_stopped:
        raise MigrationValidationError("Stop backend, scheduler and CLI workers first; --writers-stopped is required")
    source, target = read_snapshot(source_path), read_snapshot(backup_path)
    plan, additions = plan_merge(source, target, approved.get("decisions", {}))
    for field in ("source_digest", "target_digest", "tables", "project_duplicates", "blockers", "integer_id_remaps", "conflicts"):
        if plan[field] != approved.get(field):
            raise MigrationValidationError(f"Approved report differs from inputs: {field}; rerun dry-run")
    if plan["blockers"]:
        raise MigrationValidationError("Unresolved project conflicts; explicit owner decision required")
    if not approved.get("simulation", {}).get("passed"):
        raise MigrationValidationError("Approved report has no successful simulation")
    expected = {name: rows + additions[name] for name, rows in target.items()}
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL lock_timeout = '10s'"))
                connection.execute(text("SET LOCAL statement_timeout = '10min'"))
                configure_exact_float_reads(connection)
                # Locks protect against every writer, not only cooperative workers.
                names = ",".join(connection.dialect.identifier_preparer.quote_identifier(t.name)
                                  for t in tables_to_copy())
                connection.execute(text(f"LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE"))
            else:
                connection.execute(text("PRAGMA foreign_keys=ON"))
            if set(inspect(connection).get_table_names()) != set(target):
                raise MigrationValidationError("Destination table set changed since dry-run")
            current = database_rows(connection)
            if digest_snapshot(current) == digest_snapshot(expected):
                transaction.rollback()
                return {"status": "already_applied", "changed": False}
            if digest_snapshot(current) != plan["target_digest"]:
                raise MigrationValidationError("Database changed since dry-run/backup; no merge performed")
            now = datetime.now(timezone.utc)
            for lease in current["leases"]:
                expiry = lease["expires_at"]
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry > now:
                    raise MigrationValidationError("Active worker lease; stop workers and wait for lease expiry")
            for table in tables_to_copy():
                batch = additions[table.name]
                for offset in range(0, len(batch), 300):
                    connection.execute(table.insert(), batch[offset:offset + 300])
            counts = verify_merge(connection, expected)
            restart_sequences(connection)
            if apply:
                transaction.commit()
            else:
                transaction.rollback()
            return {"status": "committed" if apply else "rolled_back", "table_counts": counts,
                    "protected_projects": plan["protected_projects"], "all_target_rows_unchanged": True}
        except BaseException:
            if transaction.is_active:
                transaction.rollback()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-backup", type=Path, required=True)
    parser.add_argument("--approved-report", type=Path, required=True)
    parser.add_argument("--restore-report", type=Path, help="Successful disposable PostgreSQL restore report; required for --apply")
    parser.add_argument("--writers-stopped", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Explicitly commit; omitted means mandatory rollback")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            if args.restore_report is None:
                raise MigrationValidationError("--apply requires --restore-report from the disposable PostgreSQL restore check")
            proof = json.loads(args.restore_report.read_text())
            if (proof.get("passed") is not True or proof.get("database") != "disposable_local_postgresql_16"
                    or proof.get("snapshot_digest") != digest_snapshot(read_snapshot(args.target_backup))):
                raise MigrationValidationError("Restore verification does not match this backup")
        parsed = normalized_database_url(Settings().database_url)
        if parsed.get_backend_name() != "postgresql":
            raise MigrationValidationError("Execution requires PostgreSQL")
        engine = create_engine(parsed, connect_args={"connect_timeout": 10})
        try:
            result = execute_merge(engine, args.source, args.target_backup, json.loads(args.approved_report.read_text()),
                                   apply=args.apply, writers_stopped=args.writers_stopped)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            engine.dispose()
        return 0
    except Exception as exc:
        detail = str(exc) if isinstance(exc, MigrationValidationError) else type(exc).__name__
        print(f"Merge failed: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
