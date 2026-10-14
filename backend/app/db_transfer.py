"""Consistent SQLite backup, including committed records still in the WAL."""

import argparse
import json
from pathlib import Path
import sqlite3
from sqlalchemy.engine import make_url
from .config import ROOT


def database_path(url):
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in (None, ":memory:"):
        raise ValueError("Transfer requires a file-backed SQLite database")
    return Path(parsed.database).resolve()


def snapshot(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if target.exists() or target == source:
        raise ValueError("Refusing to overwrite an existing file")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents overwriting a file created after the check.
    with target.open("xb"):
        pass
    target.chmod(0o600)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
        target.chmod(0o600)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Export consistent SQLite data (including committed WAL)")
    parser.add_argument("--source", type=Path, default=ROOT / "data/finder.sqlite3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot(args.source, args.output)
    print(json.dumps({"exported": str(args.output), "bytes": args.output.stat().st_size}))


if __name__ == "__main__":
    main()
