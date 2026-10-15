"""Non-destructive recovery tools for a failed cross-database transfer."""

import json
import sqlite3
from pathlib import Path

from sqlalchemy import DateTime, create_engine, func, inspect, select, text

from .db import Base
from .migrations import migrate
from .sqlite_postgres_migration import (
    MigrationValidationError, _insert_batch, compare_table, configure_exact_float_reads, fingerprint,
    key_for, source_row, tables_to_copy, validate_source, validate_test_target,
)


def export_target(engine, destination: Path):
    """Read a consistent PostgreSQL snapshot and verify an isolated SQLite backup."""
    validate_test_target(engine)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an earlier backup, including a concurrently created one.
    with destination.open("xb"):
        pass
    destination.chmod(0o600)
    backup_engine = create_engine(f"sqlite:///{destination}")
    counts = {}
    try:
        validate_test_target(backup_engine)
        migrate(backup_engine, Base.metadata)
        with engine.begin() as original, backup_engine.begin() as backup:
            if engine.dialect.name == "postgresql":
                original.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            configure_exact_float_reads(original)
            backup.execute(text("PRAGMA foreign_keys=ON"))
            present = set(inspect(original).get_table_names())
            for table in tables_to_copy():
                if table.name not in present:
                    raise MigrationValidationError(f"Export source table missing: {table.name}")
                columns = {column["name"] for column in inspect(original).get_columns(table.name)}
                if columns != set(table.columns.keys()):
                    raise MigrationValidationError(f"Export source columns differ: {table.name}")
                hashes, batch = {}, []
                for row in original.execute(select(table)).mappings():
                    item = source_row(row, table)
                    hashes[key_for(item, table)] = fingerprint(item, table)
                    batch.append(item)
                    if len(batch) == 300:
                        _insert_batch(backup, table, batch)
                        batch.clear()
                _insert_batch(backup, table, batch)
                original_count = len(hashes)
                backup_count = backup.scalar(select(func.count()).select_from(table))
                for row in backup.execute(select(table)).mappings():
                    if hashes.pop(key_for(row, table), None) != fingerprint(row, table):
                        raise MigrationValidationError(f"Export verification failed: {table.name}")
                if hashes or original_count != backup_count:
                    raise MigrationValidationError(f"Export counts differ: {table.name}")
                counts[table.name] = original_count
        with sqlite3.connect(f"file:{destination}?mode=ro", uri=True) as backup:
            validate_source(backup, tables_to_copy())
        return counts
    except Exception:
        backup_engine.dispose()
        destination.unlink(missing_ok=True)
        raise
    finally:
        backup_engine.dispose()


def temporary_table_sql(preparer, schema, name):
    """Names come only from the application's reviewed schema metadata."""
    quoted = preparer.quote_identifier(name)
    origin = f"{preparer.quote_schema(schema)}.{quoted}"
    return f"CREATE TEMP TABLE {quoted} (LIKE {origin} INCLUDING ALL) ON COMMIT DROP"


def rehearse_transfer(source_path: Path, engine):
    """Reproduce PostgreSQL conversion in pg_temp; always roll back all temp DDL/data.

    Explicit values are supplied for every column. Consequently copied SERIAL
    defaults cannot consume production sequences. No sequence reset is called.
    """
    validate_test_target(engine)
    if engine.dialect.name != "postgresql":
        raise MigrationValidationError("Rehearsal requires PostgreSQL temporary tables")
    tables = tables_to_copy()
    with sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        validate_source(source, tables)
        with engine.connect() as target:
            transaction = target.begin()
            try:
                target.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                previous_float_digits = configure_exact_float_reads(target)
                inspector = inspect(target)
                schema = inspector.default_schema_name
                present = set(inspector.get_table_names(schema=schema))
                timezone_flags = {}
                for table in tables:
                    if table.name not in present:
                        raise MigrationValidationError(f"Rehearsal source table missing: {table.name}")
                    definitions = inspector.get_columns(table.name, schema=schema)
                    columns = {column["name"] for column in definitions}
                    if columns != set(table.columns.keys()):
                        raise MigrationValidationError(f"Rehearsal columns differ: {table.name}")
                    timezone_flags[table.name] = {
                        column["name"]: column["type"].timezone
                        for column in definitions if isinstance(column["type"], DateTime)
                    }
                    target.execute(text(temporary_table_sql(target.dialect.identifier_preparer, schema, table.name)))
                # All unqualified INSERT/SELECT names now resolve exclusively to
                # temporary tables, with built-in functions from pg_catalog.
                target.execute(text("SET LOCAL search_path TO pg_temp, pg_catalog"))
                report = {"mode": "temporary_postgres_rehearsal", "production_rows_modified": False,
                          "sequences_modified": False, "session_timezone": target.scalar(text("SHOW TIME ZONE")),
                          "extra_float_digits_before": previous_float_digits,
                          "extra_float_digits_effective": target.scalar(text("SHOW extra_float_digits")),
                          "tables": {}}
                for table in tables:
                    batch = []
                    for row in source.execute(f'SELECT * FROM "{table.name}"'):
                        batch.append(source_row(row, table))
                        if len(batch) == 300:
                            _insert_batch(target, table, batch)
                            batch.clear()
                    _insert_batch(target, table, batch)
                    result = compare_table(source, target, table)
                    report["tables"][table.name] = {
                        "sqlite_rows": source.execute(f'SELECT COUNT(*) FROM "{table.name}"').fetchone()[0],
                        "temporary_rows": target.scalar(select(func.count()).select_from(table)),
                        **result,
                        "timestamp_timezone_aware": timezone_flags[table.name],
                    }
                report["passed"] = all(
                    not any(item[key] for key in ("missing", "extra", "changed"))
                    for item in report["tables"].values()
                )
                print(json.dumps(report, indent=2))
                return report
            finally:
                # Rollback even when validation fails, or the client interrupts.
                transaction.rollback()
