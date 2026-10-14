"""Fake pg_dump subprocesses only; no production database is contacted."""

import subprocess
import sys

import pytest

from scripts.backup_postgres import dump_database


def fake_dump(payload, captured):
    def popen(command, **kwargs):
        captured.update(command=command, env=kwargs['env'])
        return subprocess.Popen([sys.executable, '-c', f'import sys;sys.stdout.buffer.write({payload!r})'],
                                **kwargs)
    return popen


def test_dump_passes_credentials_only_in_environment_and_uses_private_unique_files(tmp_path):
    captured = {}
    url = 'postgresql://user:sentinel-test-password@not-a-real-host.invalid:5432/fixture?sslmode=require'
    first = dump_database(url, tmp_path, popen=fake_dump(b'PGDMP-test-fixture', captured))
    second = dump_database(url, tmp_path, popen=fake_dump(b'PGDMP-test-fixture', {}))
    assert first != second and first.read_bytes() == b'PGDMP-test-fixture'
    assert first.stat().st_mode & 0o777 == 0o600
    assert 'sentinel-test-password' not in repr(captured['command'])
    assert 'not-a-real-host' not in repr(captured['command'])
    assert captured['env']['PGPASSWORD'] == 'sentinel-test-password'
    assert 'DATABASE_URL' not in captured['env']
    assert '--schema=public' in captured['command']


def test_size_exhaustion_removes_partial_backup(tmp_path):
    with pytest.raises(RuntimeError, match='backup_size_limit'):
        dump_database('postgresql://example.invalid/db', tmp_path, max_bytes=1,
                      popen=fake_dump(b'PGDMP-too-large', {}))
    assert not list(tmp_path.iterdir())


def test_real_pg_dump_is_forbidden_in_tests(tmp_path):
    with pytest.raises(RuntimeError, match='Tests cannot invoke'):
        dump_database('postgresql://example.invalid/db', tmp_path)
    assert not list(tmp_path.iterdir())


def test_failed_pg_dump_does_not_leave_a_misleading_dump(tmp_path):
    def failed(command, **kwargs):
        return subprocess.Popen([sys.executable, '-c', 'raise SystemExit(1)'], **kwargs)
    with pytest.raises(RuntimeError, match='pg_dump_failed'):
        dump_database('postgresql://example.invalid/db', tmp_path, popen=failed)
    assert not list(tmp_path.iterdir())
