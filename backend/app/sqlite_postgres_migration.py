"""Copy a consistent SQLite snapshot into an empty PostgreSQL catalog.

All source columns are required and copied. Existing matching rows make a
second run harmless; conflicting or extra destination data aborts the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, MetaData, String, Table, create_engine, func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .config import ROOT, Settings
from .db import Base, normalized_database_url
from .db_transfer import snapshot
from .migrations import migrate


class MigrationValidationError(ValueError):
    """Only application-authored, credential-free messages may be displayed."""


def validate_test_target(target_engine):
    if (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("IZLANISH_TEST_MODE") == "1") and (
        target_engine.dialect.name != "sqlite"
        or not Path(target_engine.url.database or "").resolve().is_relative_to(
            Path(tempfile.gettempdir()).resolve()
        )
    ):
        raise RuntimeError("Migration tests may use only an isolated temporary SQLite database")


def configure_exact_float_reads(connection):
    """Request round-trip float output, without rounding or relaxing verification.

    PostgreSQL text results can lose binary64 precision with extra_float_digits=0
    (or negative values). SET LOCAL only affects this transaction, not the server
    or future users of the pooled connection.
    """
    if connection.dialect.name != "postgresql":
        return None
    previous = connection.scalar(text("SHOW extra_float_digits"))
    connection.execute(text("SET LOCAL extra_float_digits = 3"))
    return previous


def compare_table(source, target, table):
    source_hashes = {}
    for row in source.execute(f'SELECT * FROM "{table.name}"'):
        item = source_row(row, table)
        source_hashes[key_for(item, table)] = fingerprint(item, table)
    result = {"missing": 0, "extra": 0, "changed": 0, "fields": {}, "samples": [],
              "numeric_max_abs_delta": {}, "timestamp_max_abs_delta_seconds": {}}
    for row in target.execute(select(table)).mappings():
        key = key_for(row, table)
        expected = source_hashes.pop(key, None)
        if expected is None:
            result["extra"] += 1
        elif expected != fingerprint(row, table):
            result["changed"] += 1
            where = " AND ".join(f'"{column.name}"=?' for column in table.primary_key.columns)
            original = source_row(source.execute(
                f'SELECT * FROM "{table.name}" WHERE {where}', key
            ).fetchone(), table)
            fields = []
            for column in table.columns:
                before, after = original[column.name], row[column.name]
                if json.dumps(canonical(before), sort_keys=True) != json.dumps(canonical(after), sort_keys=True):
                    fields.append(column.name)
                    label = f"{column.name} ({type(before).__name__}->{type(after).__name__})"
                    result["fields"][label] = result["fields"].get(label, 0) + 1
                    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                        deltas = result["numeric_max_abs_delta"]
                        deltas[column.name] = max(deltas.get(column.name, 0), abs(before - after))
                    if isinstance(before, datetime) and isinstance(after, datetime):
                        left = before.replace(tzinfo=timezone.utc) if before.tzinfo is None else before
                        right = after.replace(tzinfo=timezone.utc) if after.tzinfo is None else after
                        deltas = result["timestamp_max_abs_delta_seconds"]
                        deltas[column.name] = max(deltas.get(column.name, 0), abs((left - right).total_seconds()))
            if len(result["samples"]) < 3:
                # URLs are primary keys in some tables; never print their contents.
                digest = hashlib.sha256(repr(key).encode()).hexdigest()[:16]
                result["samples"].append({"row_key_hash": digest, "columns": fields})
    result["missing"] = len(source_hashes)
    return result


def diagnose_database(source_path, target_engine):
    """Compare the existing databases without creating tables or modifying rows."""
    validate_test_target(target_engine)
    with sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        tables = tables_to_copy()
        validate_source(source, tables)
        with target_engine.begin() as target:
            if target.dialect.name == "postgresql":
                target.execute(text("SET TRANSACTION READ ONLY"))
            configure_exact_float_reads(target)
            present = set(inspect(target).get_table_names())
            report = {}
            for table in tables:
                if table.name not in present:
                    report[table.name] = {"table_missing": True}
                    continue
                counts = {
                    "sqlite_rows": source.execute(f'SELECT COUNT(*) FROM "{table.name}"').fetchone()[0],
                    "target_rows": target.scalar(select(func.count()).select_from(table)),
                }
                types = {column["name"]: str(column["type"]) for column in inspect(target).get_columns(table.name)}
                report[table.name] = {
                    **counts, **compare_table(source, target, table),
                    "target_numeric_date_types": {
                        column.name: types[column.name] for column in table.columns
                        if isinstance(column.type, (Float, DateTime))
                    },
                }
            print(json.dumps(report, indent=2))
            return report


def tables_to_copy():
    versions = Table("schema_migrations", MetaData(),
                     Column("version", Integer, primary_key=True), Column("applied_at", String(80), nullable=False))
    return [versions, *Base.metadata.sorted_tables]


def source_tables(source):
    return {name for (name,) in source.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def convert_value(value, column):
    if value is None:
        return None
    if isinstance(column.type, JSON):
        return json.loads(value) if isinstance(value, str) else value
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime):
        moment = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)
    return value


def source_row(row, table):
    return {column.name: convert_value(row[column.name], column) for column in table.columns}


def canonical(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def fingerprint(row, table):
    names = [column.name for column in table.columns]
    payload = {name: canonical(row[name]) for name in names}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def key_for(row, table):
    return tuple(row[column.name] for column in table.primary_key.columns)


def validate_source(source, tables):
    if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise MigrationValidationError("SQLite integrity_check failed")
    if source.execute("PRAGMA foreign_key_check").fetchone():
        raise MigrationValidationError("SQLite foreign_key_check failed")
    expected = {table.name for table in tables}
    actual = source_tables(source)
    if expected != actual:
        raise MigrationValidationError("SQLite table set differs from the application schema")
    for table in tables:
        columns = {row[1] for row in source.execute(f'PRAGMA table_info("{table.name}")')}
        if columns != set(table.columns.keys()):
            raise MigrationValidationError(f"SQLite columns differ for {table.name}")


def _insert_batch(connection, table, batch):
    if not batch:
        return
    if connection.dialect.name == "postgresql":
        statement = pg_insert(table)
    elif connection.dialect.name == "sqlite":
        statement = sqlite_insert(table)
    else:
        raise ValueError("Unsupported migration target")
    if table.name == "schema_migrations":
        statement = statement.on_conflict_do_update(
            index_elements=list(table.primary_key.columns),
            set_={"applied_at": statement.excluded.applied_at},
        )
    else:
        statement = statement.on_conflict_do_nothing(index_elements=list(table.primary_key.columns))
    connection.execute(statement, batch)


def _reset_sequences(connection, tables):
    if connection.dialect.name != "postgresql":
        return
    for table in tables:
        for column in table.primary_key.columns:
            if not isinstance(column.type, Integer) or not column.autoincrement:
                continue
            sequence = connection.scalar(text("SELECT pg_get_serial_sequence(:table, :column)"),
                                         {"table": table.name, "column": column.name})
            if sequence:
                maximum = connection.scalar(select(func.max(column)))
                connection.execute(text("SELECT setval(CAST(:sequence AS regclass), :value, :called)"),
                                   {"sequence": sequence, "value": maximum or 1, "called": maximum is not None})


def copy_and_verify(source_path: Path, target_engine):
    """Migrate all rows in one transaction; a test may supply temporary SQLite."""
    validate_test_target(target_engine)
    tables = tables_to_copy()
    with sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        validate_source(source, tables)
        expected_identity = source.execute(
            "SELECT instance_uuid FROM database_identity WHERE id='primary'").fetchone()
        # Refuse a different live database before even applying schema migrations.
        with target_engine.connect() as preflight:
            if "database_identity" in inspect(preflight).get_table_names():
                current_identity = preflight.scalar(text(
                    "SELECT instance_uuid FROM database_identity WHERE id='primary'"))
                if current_identity and (not expected_identity or current_identity != expected_identity[0]):
                    raise MigrationValidationError("Destination database identity differs from the SQLite source. No schema or data changed; run --diagnose. Do not delete existing projects.")
        migrate(target_engine, Base.metadata)
        with target_engine.begin() as target:
            configure_exact_float_reads(target)
            if target.dialect.name == "postgresql":
                target.execute(text("SELECT pg_advisory_xact_lock(hashtext('izlanish_sqlite_migration'))"))
            current_identity = target.scalar(text(
                "SELECT instance_uuid FROM database_identity WHERE id='primary'"))
            if current_identity and (not expected_identity or current_identity != expected_identity[0]):
                raise MigrationValidationError("Destination database identity differs from the SQLite source. No data copied; run --diagnose. Do not delete existing projects.")
            if not current_identity and any(target.scalar(select(func.count()).select_from(
                    table)) for table in tables if table.name not in {"schema_migrations", "database_identity"}):
                raise MigrationValidationError("Destination has application rows without matching database identity. No data copied; run --diagnose.")

            for table in tables:
                batch = []
                for row in source.execute(f'SELECT * FROM "{table.name}"'):
                    batch.append(source_row(row, table))
                    if len(batch) >= 300:
                        _insert_batch(target, table, batch)
                        batch.clear()
                _insert_batch(target, table, batch)
            counts = []
            mismatch = False
            differences = {}
            for table in tables:
                original = source.execute(f'SELECT COUNT(*) FROM "{table.name}"').fetchone()[0]
                migrated = target.scalar(select(func.count()).select_from(table))
                counts.append((table.name, original, migrated))
                if original != migrated:
                    mismatch = True
                    continue
                result = compare_table(source, target, table)
                if any(result[name] for name in ("missing", "extra", "changed")):
                    mismatch = True
                    differences[table.name] = result
            target_label = "PostgreSQL" if target.dialect.name == "postgresql" else "SQLite test"
            print(f"{'table':<28} {'SQLite':>10} {target_label:>12}")
            for name, original, migrated in counts:
                print(f"{name:<28} {original:>10} {migrated:>12}")
            if mismatch:
                print("Value differences (no row values or credentials):")
                print(json.dumps(differences, indent=2))
                raise MigrationValidationError("Destination rows or values differ from the SQLite source; transaction rolled back")
            _reset_sequences(target, tables)
            print("Verified: all table rows, project IDs and publication timestamps match the SQLite source.")
            return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Copy every SQLite table into PostgreSQL without losing IDs")
    parser.add_argument("--source", type=Path, default=ROOT / "data/migration-source.sqlite3")
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "data/backups")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--diagnose", action="store_true", help="Read-only comparison; does not create schema, copy data or reset sequences")
    modes.add_argument("--rehearse", action="store_true", help="Reproduce transfer in PostgreSQL temporary tables; always rolls back and leaves production data unchanged")
    modes.add_argument("--export-target", type=Path, help="Read-only consistent export of the existing PostgreSQL data into a new SQLite backup")
    args = parser.parse_args(argv)
    try:
        source = args.source.resolve()
        if not args.export_target and not source.is_file():
            raise MigrationValidationError("SQLite source file is missing")
        settings = Settings()
        parsed = normalized_database_url(settings.database_url)
        if parsed.get_backend_name() != "postgresql":
            raise ValueError("DATABASE_URL must point to PostgreSQL for this command")
        engine = create_engine(parsed, pool_pre_ping=True, connect_args={"connect_timeout": 10})
        try:
            if args.diagnose:
                diagnose_database(source, engine)
            elif args.export_target:
                from .migration_recovery import export_target

                counts = export_target(engine, args.export_target)
                print(json.dumps({"backup": str(args.export_target), "tables": counts}, indent=2))
            elif args.rehearse:
                from .migration_recovery import rehearse_transfer

                report = rehearse_transfer(source, engine)
                if not report["passed"]:
                    return 1
            else:
                args.backup_dir.mkdir(parents=True, exist_ok=True)
                backup = args.backup_dir / f"migration-source-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.sqlite3"
                snapshot(source, backup)
                print("SQLite backup created:", backup)
                copy_and_verify(backup, engine)
        finally:
            engine.dispose()
        return 0
    except Exception as exc:
        # SQLAlchemy/driver exception text may contain connection details.
        original = getattr(exc, "orig", exc)
        state = getattr(original, "sqlstate", None)
        detail = str(exc) if isinstance(exc, MigrationValidationError) else type(exc).__name__
        print(f"Migration failed: {detail}" + (f" (SQLSTATE {state})" if state else ""),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
