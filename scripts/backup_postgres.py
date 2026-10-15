#!/usr/bin/env python3
"""Bounded pg_dump of public application tables; never prints a connection URL."""

import argparse
import os
from pathlib import Path
import selectors
import subprocess
import sys
from time import monotonic
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.engine import make_url


class BackupFailure(RuntimeError):
    """Application-owned safe error code, never driver/server output."""


def dump_database(url, directory, *, docker_client=False, max_bytes=20 * 1024 * 1024, seconds=180, popen=subprocess.Popen):
    if os.environ.get("PYTEST_CURRENT_TEST") and popen is subprocess.Popen:
        raise RuntimeError("Tests cannot invoke a real production pg_dump")
    parsed = make_url(url)
    if parsed.get_backend_name() not in {"postgres", "postgresql"}:
        raise BackupFailure("postgresql_url_required")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"izlanish-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.dump"
    env = {**os.environ, "PGHOST": parsed.host or "", "PGPORT": str(parsed.port or 5432),
           "PGDATABASE": parsed.database or "postgres", "PGUSER": parsed.username or "",
           "PGPASSWORD": parsed.password or "", "PGSSLMODE": parsed.query.get("sslmode", "require"),
           "PGCONNECT_TIMEOUT": "10"}
    # DATABASE_URL itself is not inherited by pg_dump/container tooling.
    env.pop("DATABASE_URL", None)
    env.pop("BACKUP_ENCRYPTION_PASSPHRASE", None)
    command = ["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--no-acl", "--schema=public"]
    container = None
    if docker_client:
        container = "izlanish-backup-" + uuid4().hex[:12]
        prefix = ["docker", "run", "--rm", "--name", container]
        for name in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE", "PGCONNECT_TIMEOUT"):
            prefix.extend(["--env", name])
        command = prefix + ["postgres:18", *command]
    process = None
    try:
        with path.open("xb") as output:
            path.chmod(0o600)
            process = popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            total, deadline = 0, monotonic() + seconds
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    if monotonic() >= deadline:
                        raise BackupFailure("backup_time_limit")
                    if not selector.select(timeout=1):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise BackupFailure("backup_size_limit")
                    output.write(chunk)
            if process.wait(timeout=max(1, deadline - monotonic())) != 0:
                raise BackupFailure("pg_dump_failed")
            if total == 0:
                raise BackupFailure("empty_backup")
        with path.open("rb") as saved:
            if saved.read(5) != b"PGDMP":
                raise BackupFailure("invalid_dump_format")
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if process.stdout:
                process.stdout.close()
        if container:
            subprocess.run(["docker", "rm", "--force", container], env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/backups"))
    parser.add_argument("--docker-client", action="store_true")
    args = parser.parse_args()
    try:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise BackupFailure("database_url_missing")
        path = dump_database(url, args.directory, docker_client=args.docker_client,
                             max_bytes=min(int(os.environ.get("BACKUP_MAX_BYTES", 20 * 1024 * 1024)), 100 * 1024 * 1024),
                             seconds=min(int(os.environ.get("BACKUP_MAX_SECONDS", 180)), 300))
        print(path)
        return 0
    except Exception as exc:
        # Neither driver output nor URL/PGPASSWORD are included.
        print("Backup failed: " + (str(exc) if isinstance(exc, BackupFailure) else type(exc).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
