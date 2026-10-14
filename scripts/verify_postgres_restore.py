#!/usr/bin/env python3
"""Restore a backup ONLY into a new disposable localhost Docker PostgreSQL.

DATABASE_URL is never read. No production credentials or volumes are used.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.app.merge_dry_run import digest_snapshot, read_snapshot  # noqa: E402
from backend.app.merge_execute import database_rows  # noqa: E402
from backend.app.sqlite_postgres_migration import (  # noqa: E402
    MigrationValidationError, configure_exact_float_reads, copy_and_verify,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = read_snapshot(args.backup)
    if args.report.exists():
        raise MigrationValidationError("Report already exists")
    name = "izlanish-restore-" + uuid4().hex[:12]
    engine = None
    created = False
    try:
        subprocess.run(["docker", "run", "--detach", "--name", name, "--publish", "127.0.0.1::5432",
                        "--tmpfs", "/var/lib/postgresql/data", "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
                        "--env", "POSTGRES_DB=restore_check", "postgres:16"], check=True, capture_output=True)
        created = True
        binding = subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True).strip()
        if not binding.startswith("127.0.0.1:") or not binding.split(":")[-1].isdigit():
            raise MigrationValidationError("Unexpected disposable container binding")
        port = int(binding.split(":")[-1])
        engine = create_engine(f"postgresql+psycopg://postgres@127.0.0.1:{port}/restore_check",
                               connect_args={"connect_timeout": 2})
        for _ in range(30):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                break
            except Exception:
                time.sleep(1)
        else:
            raise MigrationValidationError("Disposable PostgreSQL did not become ready")
        counts = copy_and_verify(args.backup, engine)
        repeated = copy_and_verify(args.backup, engine)
        if repeated != counts:
            raise MigrationValidationError("Restore rerun changed counts")
        with engine.begin() as connection:
            configure_exact_float_reads(connection)
            restored = database_rows(connection)
        if digest_snapshot(restored) != digest_snapshot(source):
            raise MigrationValidationError("Restored backup values differ")
        result = {"passed": True, "database": "disposable_local_postgresql_16", "production_accessed": False,
                  "snapshot_digest": digest_snapshot(source),
                  "idempotent": True, "all_values_match": True,
                  "tables": {table: {"backup": before, "restored": after} for table, before, after in counts},
                  "projects": [{"id": row["id"], "name": row["name"], "published_at": str(row["published_at"])}
                               for row in source["projects"]]}
        with args.report.open("x") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
        print(f"Restore verified. Report: {args.report}")
    finally:
        if engine:
            engine.dispose()
        if created:
            subprocess.run(["docker", "rm", "--force", name], check=True, capture_output=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Restore verification failed: " + (str(exc) if isinstance(exc, MigrationValidationError)
                                                else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1)
