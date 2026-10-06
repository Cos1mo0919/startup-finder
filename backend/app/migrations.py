"""Versioned, idempotent initial→radar migration. DDL is fixed, never user input."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import inspect, text

ADDITIONS = {
    "projects": {
        "primary_sector": "VARCHAR(50) NOT NULL DEFAULT 'other'",
        "sectors": "JSON NOT NULL DEFAULT '[]'",
        "visible": "BOOLEAN NOT NULL DEFAULT FALSE",
        "stop_reasons": "JSON NOT NULL DEFAULT '[]'",
        "detection_signals": "JSON NOT NULL DEFAULT '[]'",
        "real_project_confidence": "FLOAT NOT NULL DEFAULT 0",
        "event_id": "VARCHAR(36) REFERENCES events(id)",
    },
    "project_sources": {"source_id": "VARCHAR(80) REFERENCES sources(id)"},
    "candidates": {
        "source_id": "VARCHAR(80) REFERENCES sources(id)",
        "event_id": "VARCHAR(36) REFERENCES events(id)",
    },
}


def migrate(engine, metadata):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    legacy = "sources" in tables and "project_id" in {c["name"] for c in inspector.get_columns("sources")}
    if legacy and engine.dialect.name == "sqlite" and engine.url.database != ":memory:":
        path = Path(engine.url.database)
        backup = path.with_name(path.name + ".pre-radar-backup")
        if not backup.exists():
            with sqlite3.connect(path) as src, sqlite3.connect(backup) as target:
                src.backup(target)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at VARCHAR(80) NOT NULL)"
            )
        )
        if legacy:
            conn.execute(text("ALTER TABLE sources RENAME TO project_sources"))
        metadata.create_all(conn)
        for table, additions in ADDITIONS.items():
            columns = {c["name"] for c in inspect(conn).get_columns(table)}
            for name, definition in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=2")) is None:
            conn.execute(
                text("INSERT INTO schema_migrations(version,applied_at) VALUES(2,:at)"),
                {"at": datetime.now(timezone.utc).isoformat()},
            )
