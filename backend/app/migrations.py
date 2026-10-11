"""Versioned, idempotent initial→radar migration. DDL is fixed, never user input."""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
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
        "problem_statement": "TEXT NOT NULL DEFAULT ''",
        "problem_subject": "VARCHAR(300) NOT NULL DEFAULT ''",
        "problem_scope": "VARCHAR(40) NOT NULL DEFAULT ''",
        "problem_frequency": "VARCHAR(100) NOT NULL DEFAULT ''",
        "problem_severity": "VARCHAR(100) NOT NULL DEFAULT ''",
        "problem_evidence_summary": "TEXT NOT NULL DEFAULT ''",
        "problem_gate_status": "VARCHAR(30) NOT NULL DEFAULT 'PENDING'",
        "problem_gate_reason": "VARCHAR(100) NOT NULL DEFAULT 'pending_problem_analysis'",
        "opportunity_score": "FLOAT",
        "opportunity_grade": "VARCHAR(20) NOT NULL DEFAULT 'PENDING'",
        "opportunity_details": "JSON NOT NULL DEFAULT '{}'",
        "publication_status": "VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED'",
        "publication_reason": "VARCHAR(100) NOT NULL DEFAULT ''",
        "secondary_problems": "JSON NOT NULL DEFAULT '[]'",
        "discovery_source_url": "TEXT",
        "analysis_method": "VARCHAR(20) NOT NULL DEFAULT 'legacy'",
        "catalog_score": "FLOAT",
        "evidence_count": "INTEGER NOT NULL DEFAULT 0",
        "classification_confidence": "FLOAT",
        "catalog_scores": "JSON NOT NULL DEFAULT '{}'",
        "catalog_score_reasons": "JSON NOT NULL DEFAULT '{}'",
        "score_evidence": "JSON NOT NULL DEFAULT '{}'",
        "score_pending": "BOOLEAN NOT NULL DEFAULT TRUE",
        "short_description": "TEXT NOT NULL DEFAULT ''",
        "description_needs_translation": "BOOLEAN NOT NULL DEFAULT FALSE",
        "date_estimated": "BOOLEAN NOT NULL DEFAULT FALSE",
        "publication_method": "VARCHAR(25) NOT NULL DEFAULT 'automated'",
        "sector_method": "VARCHAR(20) NOT NULL DEFAULT 'keyword'",
        "project_type": "VARCHAR(30) NOT NULL DEFAULT 'other'",
        "project_type_method": "VARCHAR(20) NOT NULL DEFAULT 'source_context'",
        "project_stage": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        "review_reason": "VARCHAR(100) NOT NULL DEFAULT ''",
        "publication_excerpt": "TEXT NOT NULL DEFAULT ''",
        "classification_history": "JSON NOT NULL DEFAULT '[]'",
        "status_history": "JSON NOT NULL DEFAULT '[]'",
        "attribute_history": "JSON NOT NULL DEFAULT '[]'",
        "reanalysis_state": "VARCHAR(30) NOT NULL DEFAULT ''",
        "reanalysis_attempts": "INTEGER NOT NULL DEFAULT 0",
        "reanalysis_next_at": "DATETIME",
    },
    "project_sources": {"source_id": "VARCHAR(80) REFERENCES sources(id)"},
    "runs": {"details": "JSON NOT NULL DEFAULT '{}'"},
    "candidates": {
        "origin": "VARCHAR(40) NOT NULL DEFAULT 'other'",
        "processing_version": "INTEGER NOT NULL DEFAULT 0",
        "analysis_mode": "VARCHAR(20) NOT NULL DEFAULT ''",
        "last_run_id": "INTEGER",
        "archive_scope": "JSON NOT NULL DEFAULT '[]'",
        "source_id": "VARCHAR(80) REFERENCES sources(id)",
        "event_id": "VARCHAR(36) REFERENCES events(id)",
        "entity_type": "VARCHAR(30) NOT NULL DEFAULT 'IGNORE'",
        "project_ids": "JSON NOT NULL DEFAULT '[]'",
        "detector_result": "VARCHAR(30) NOT NULL DEFAULT 'NEEDS_EXTRACTION'",
        "review_decision": "VARCHAR(30) NOT NULL DEFAULT ''",
        "classification_confidence": "FLOAT",
        "classification_history": "JSON NOT NULL DEFAULT '[]'",
        "status_history": "JSON NOT NULL DEFAULT '[]'",
    },
    "sources": {
        "country": "VARCHAR(100) NOT NULL DEFAULT ''",
        "sector": "VARCHAR(80) NOT NULL DEFAULT ''",
        "purpose": "TEXT NOT NULL DEFAULT ''",
        "provides_projects": "BOOLEAN NOT NULL DEFAULT FALSE",
        "provides_problem_signals": "BOOLEAN NOT NULL DEFAULT FALSE",
        "provides_market_signals": "BOOLEAN NOT NULL DEFAULT FALSE",
        "parser_type": "VARCHAR(80) NOT NULL DEFAULT ''",
        "last_error_at": "DATETIME",
        "last_http_status": "INTEGER",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    },
    "ecosystem_signals": {
        "summary_uz": "TEXT NOT NULL DEFAULT ''",
        "why_it_matters_uz": "TEXT NOT NULL DEFAULT ''",
        "country": "VARCHAR(100) NOT NULL DEFAULT 'Uzbekistan'",
        "region": "VARCHAR(120) NOT NULL DEFAULT ''",
        "sector": "VARCHAR(80) NOT NULL DEFAULT ''",
        "confidence": "FLOAT NOT NULL DEFAULT 0",
        "intelligence_status": "VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'",
    },
    "problems": {"first_evidence_published_at": "DATETIME"},
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
    if engine.dialect.name == "sqlite" and engine.url.database != ":memory:":
        current = inspect(engine)
        if "project_sources" in current.get_table_names() and any(
            set(item.get("column_names") or []) == {"url"}
            for item in current.get_unique_constraints("project_sources")
        ):
            path = Path(engine.url.database)
            backup = path.with_name(path.name + ".pre-multisource-backup")
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

        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=3")) is None:
            conn.execute(
                text("INSERT INTO schema_migrations(version,applied_at) VALUES(3,:at)"),
                {"at": datetime.now(timezone.utc).isoformat()},
            )
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=4")) is None:
            conn.execute(
                text("INSERT INTO schema_migrations(version,applied_at) VALUES(4,:at)"),
                {"at": datetime.now(timezone.utc).isoformat()},
            )
        constraints = inspect(conn).get_unique_constraints("project_sources")
        url_only = next((item for item in constraints if set(item.get("column_names") or []) == {"url"}), None)
        if url_only:
            if engine.dialect.name == "sqlite":
                conn.execute(text("""CREATE TABLE project_sources_multi (
                    id INTEGER PRIMARY KEY, project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    url TEXT NOT NULL, publisher VARCHAR(300) NOT NULL, kind VARCHAR(30) NOT NULL,
                    published_at DATETIME NOT NULL, retrieved_at DATETIME NOT NULL,
                    quotes JSON NOT NULL, source_id VARCHAR(80) REFERENCES sources(id),
                    UNIQUE(project_id, url))"""))
                conn.execute(text("""INSERT INTO project_sources_multi
                    (id,project_id,url,publisher,kind,published_at,retrieved_at,quotes,source_id)
                    SELECT id,project_id,url,publisher,kind,published_at,retrieved_at,quotes,source_id
                    FROM project_sources"""))
                conn.execute(text("DROP TABLE project_sources"))
                conn.execute(text("ALTER TABLE project_sources_multi RENAME TO project_sources"))
                conn.execute(text("CREATE INDEX ix_project_sources_project_id ON project_sources(project_id)"))
            else:
                name = url_only.get("name")
                if name:
                    quoted = conn.dialect.identifier_preparer.quote(name)
                    conn.execute(text(f"ALTER TABLE project_sources DROP CONSTRAINT {quoted}"))
                conn.execute(text("ALTER TABLE project_sources ADD CONSTRAINT uq_project_source_url UNIQUE (project_id, url)"))
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=5")) is None:
            conn.execute(text("INSERT INTO schema_migrations(version,applied_at) VALUES(5,:at)"),
                         {"at": datetime.now(timezone.utc).isoformat()})
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=6")) is None:
            conn.execute(text("INSERT INTO schema_migrations(version,applied_at) VALUES(6,:at)"),
                         {"at": datetime.now(timezone.utc).isoformat()})
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=7")) is None:
            conn.execute(text("INSERT INTO schema_migrations(version,applied_at) VALUES(7,:at)"),
                         {"at": datetime.now(timezone.utc).isoformat()})
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=8")) is None:
            conn.execute(text("INSERT INTO schema_migrations(version,applied_at) VALUES(8,:at)"),
                         {"at": datetime.now(timezone.utc).isoformat()})
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=9")) is None:
            conn.execute(text("INSERT INTO schema_migrations(version,applied_at) VALUES(9,:at)"),
                         {"at": datetime.now(timezone.utc).isoformat()})
        if conn.scalar(text("SELECT version FROM schema_migrations WHERE version=10")) is None:
            # Backfill only publication transitions that are supported by saved
            # history. First-seen is a conservative fallback for legacy cards.
            totals = {}
            for row in conn.execute(text("SELECT id,country,first_seen,status_history,publication_status "
                                         "FROM projects")):
                history = json.loads(row.status_history) if isinstance(row.status_history, str) else row.status_history or []
                published = [item.get("timestamp") for item in history
                             if item.get("value") in ("PUBLISHED", "AUTO_PUBLISHED") and item.get("timestamp")]
                moment = published[0] if published else row.first_seen if row.publication_status == "PUBLISHED" else None
                if not moment:
                    continue
                try:
                    parsed = datetime.fromisoformat(str(moment).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    day = parsed.astimezone(ZoneInfo("Asia/Tashkent")).date().isoformat()
                except ValueError:
                    continue
                urls = [value for (value,) in conn.execute(text(
                    "SELECT url FROM project_sources WHERE project_id=:id"), {"id": row.id})]
                hosts = {(urlsplit(url).hostname or "").lower() for url in urls}
                section = ("github" if "github.com" in hosts else "uzbekistan"
                           if any(host.endswith(".uz") for host in hosts) or row.country == "Uzbekistan"
                           else "global")
                item = totals.setdefault(day, {"published": 0, "uzbekistan": 0, "global": 0, "github": 0})
                item["published"] += 1
                item[section] += 1
            for day, values in totals.items():
                conn.execute(text("INSERT INTO daily_stats "
                    "(day,published_count,uzbekistan_count,global_count,github_count) "
                    "VALUES (:day,:published,:uzbekistan,:global,:github)"), {"day": day, **values})
            conn.execute(text("INSERT INTO schema_migrations(version,applied_at) VALUES(10,:at)"),
                         {"at": datetime.now(timezone.utc).isoformat()})
