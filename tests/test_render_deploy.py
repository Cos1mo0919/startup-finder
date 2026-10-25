"""Render readiness checks are offline and use only isolated temporary databases."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from backend.app.config import ROOT, Settings
from backend.app.db import Base, make_db
from backend.app.main import create_app
from backend.app.merge_dry_run import digest_snapshot, read_snapshot
from backend.app.postgres_security import enable_postgres_rls, table_names


def test_postgresql_rls_covers_every_application_table_without_public_policies():
    connection = Mock(dialect=postgresql.dialect())
    connection.execute.return_value.scalars.return_value = ["anon", "authenticated"]
    enable_postgres_rls(connection, Base.metadata)
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert len(table_names(Base.metadata)) == 22
    for name in table_names(Base.metadata):
        assert f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY' in statements
        for role in ("PUBLIC", '"anon"', '"authenticated"'):
            assert f'REVOKE ALL ON TABLE "{name}" FROM {role}' in statements
    assert not any("CREATE POLICY" in sql or "FORCE ROW" in sql for sql in statements)


def test_sqlite_tests_do_not_receive_postgres_security_ddl(tmp_path):
    engine, _ = make_db(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    try:
        with engine.begin() as connection:
            enable_postgres_rls(connection, Base.metadata)
    finally:
        engine.dispose()


def test_safe_first_boot_serves_frontend_and_api_without_changing_data(settings, factory, monkeypatch, tmp_path):
    from backend.app import main, migrations
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>isolated frontend</html>")
    (dist / "assets" / "test.js").write_text("console.log('isolated')")
    settings = settings.model_copy(update={"database_auto_migrate": False, "startup_data_updates_enabled": False,
                                           "scheduler_enabled": False, "frontend_dist": dist})
    before = digest_snapshot(read_snapshot(Path(factory.kw["bind"].url.database)))
    def forbidden(*_, **__):
        raise AssertionError("first boot must not run migrations, audits or discovery")
    for function in ("seed_registry", "audit_existing", "audit_signals", "migrate_existing_problems",
                     "synchronize_candidate_publication"):
        monkeypatch.setattr(main, function, forbidden)
    monkeypatch.setattr(migrations, "migrate", forbidden)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert "isolated frontend" in client.get("/").text
        assert "isolated frontend" in client.get("/loyihalar").text
        assert client.get("/assets/test.js").status_code == 200
        assert client.get("/api/projects").status_code == 200
        assert app.state.scheduler.running is False
    assert before == digest_snapshot(read_snapshot(Path(factory.kw["bind"].url.database)))


def test_no_auto_migration_refuses_unprepared_database(tmp_path):
    with pytest.raises(RuntimeError, match="schema is not ready"):
        make_db(f"sqlite:///{tmp_path / 'empty.sqlite3'}", auto_migrate=False)


def test_only_explicit_cors_origin_is_allowed(settings):
    settings = settings.model_copy(update={"cors_origins": ["https://client.example"],
                                           "startup_data_updates_enabled": False})
    with TestClient(create_app(settings)) as client:
        allowed = client.options("/api/projects", headers={"Origin": "https://client.example",
                                                         "Access-Control-Request-Method": "GET"})
        assert allowed.headers["access-control-allow-origin"] == "https://client.example"
        denied = client.options("/api/projects", headers={"Origin": "https://untrusted.example",
                                                        "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in denied.headers


def test_start_script_binds_render_port_and_refuses_missing_database_url(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    start = scripts / "start.sh"
    start.write_bytes((ROOT / "scripts/start.sh").read_bytes())
    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/dist/index.html").write_text("fixture")
    (tmp_path / ".venv/bin").mkdir(parents=True)
    executable = tmp_path / ".venv/bin/uvicorn"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    executable.chmod(0o755)
    env = {**os.environ, "PORT": "10000"}
    env.pop("DATABASE_URL", None)
    failed = subprocess.run(["bash", str(start)], env=env, text=True, capture_output=True)
    assert failed.returncode != 0 and "DATABASE_URL is required" in failed.stderr
    assert not list(tmp_path.rglob("*.sqlite*"))
    # A non-secret placeholder; the fake uvicorn never connects to any database.
    env["DATABASE_URL"] = "postgresql://example.invalid/isolated"
    result = subprocess.run(["bash", str(start)], env=env, text=True, capture_output=True, check=True)
    assert result.stdout.splitlines() == ["backend.app.main:create_app", "--factory", "--host", "0.0.0.0",
                                          "--port", "10000", "--workers", "1"]


def test_missing_database_url_settings_error_hides_other_secret_inputs():
    import secrets
    from pydantic import ValidationError
    sentinel = secrets.token_hex(16)  # random, so no key-like literal lives in the repo
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, database_url="", gemini_api_key=sentinel)
    assert "DATABASE_URL is required" in str(caught.value)
    assert sentinel not in str(caught.value)


@pytest.mark.parametrize("backend_access", [True, False])
def test_schema_readiness_requires_rls_and_backend_access_without_writes(monkeypatch, backend_access):
    from backend.app import postgres_security
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.execute.return_value.mappings.return_value = [
        {"relname": name, "relrowsecurity": True, "backend_access": backend_access}
        for name in table_names(Base.metadata)
    ]
    engine = Mock(dialect=postgresql.dialect())
    engine.connect.return_value = connection
    inspector = Mock()
    inspector.get_table_names.return_value = table_names(Base.metadata)
    inspector.get_columns.side_effect = lambda name: [{"name": column.name} for column in Base.metadata.tables[name].columns]
    monkeypatch.setattr(postgres_security, "inspect", lambda _: inspector)
    if backend_access:
        postgres_security.validate_schema_ready(engine, Base.metadata)
    else:
        with pytest.raises(RuntimeError, match="backend table-owner/BYPASSRLS role"):
            postgres_security.validate_schema_ready(engine, Base.metadata)
    assert all(str(call.args[0]).startswith("SELECT") for call in connection.execute.call_args_list)
