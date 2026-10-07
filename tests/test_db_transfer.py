import sqlite3

import pytest

from backend.app.db_transfer import database_path, snapshot


def test_snapshot_includes_committed_wal_and_preserves_source(tmp_path):
    source, target = tmp_path / "live.sqlite3", tmp_path / "backup.sqlite3"
    with sqlite3.connect(source) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("PRAGMA wal_autocheckpoint=0")
        live.execute("CREATE TABLE projects (id TEXT, first_seen TEXT)")
        live.execute("INSERT INTO projects VALUES ('stable-id', '2022-01-01')")
        live.commit()
        assert source.with_name(source.name + "-wal").stat().st_size > 0
        snapshot(source, target)
        with sqlite3.connect(target) as saved:
            assert saved.execute("SELECT * FROM projects").fetchall() == [("stable-id", "2022-01-01")]
        assert live.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
    assert target.stat().st_mode & 0o777 == 0o600


def test_snapshot_never_overwrites_existing_file(tmp_path):
    source, target = tmp_path / "live.sqlite3", tmp_path / "backup.sqlite3"
    with sqlite3.connect(source) as live:
        live.execute("CREATE TABLE projects (id TEXT)")
    target.write_text("existing backup")
    with pytest.raises(ValueError, match="overwrite"):
        snapshot(source, target)
    assert target.read_text() == "existing backup"
    with pytest.raises(ValueError, match="overwrite"):
        snapshot(source, source)


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "sqlite://", "postgresql://localhost/db"])
def test_backup_requires_file_sqlite(url):
    with pytest.raises(ValueError, match="file-backed SQLite"):
        database_path(url)
