# Daily PostgreSQL failure investigation (run107)

Production was not accessed or modified. The reported exception has no driver
message/SQLSTATE/trace; therefore its exact cause is **not yet established**.
No speculative publication/SQL rewrite has been applied.

## Audited execution path

| Path | PostgreSQL handling |
|---|---|
| free_daily / next_candidate | SQLAlchemy bound expressions, typed JSON extraction; no positional raw placeholders |
| writer / request and token reservations | ORM/Core typed updates; dict/list columns are SQLAlchemy JSON |
| free_budget database-size guard | PostgreSQL SELECT pg_database_size; SQLite PRAGMA is dialect-guarded |
| raw_discovery / catalog_store | ORM typed JSON, datetime and boolean fields; no direct psycopg dict binding |
| duplicate_decision | SQLAlchemy SELECT with selectin relationships / yield_per; needs real PostgreSQL coverage |
| daily._ensure_row | PostgreSQL dialect INSERT ON CONFLICT DO NOTHING; OR IGNORE only in SQLite branch |
| free_daily entrypoint | make_db(auto_migrate=False); schema/import/SQLite export tools do not run |

No unguarded `?`, `INSERT OR IGNORE`, `AUTOINCREMENT`, `datetime('now')` or
fetch-from-DML was found in this runtime path. This is a code audit, not proof
that a live schema/pooler/client mismatch is absent. Psycopg automatic prepared
statements (default threshold5) and pooler compatibility are another hypothesis;
the count of four processed items alone cannot establish that hypothesis.

## Diagnostics added

Both outer free_daily Run and inner catalog Run persist errors with:
`exception_class`, `driver_class`, bounded `message`, application `function`,
SHA256 `candidate_id`, and `sqlstate` when available. `details.last_error` mirrors
that safe record. DBAPI primary message is used; SQLAlchemy wrapper strings,
statements, bound parameters and frame locals are never logged. Quoted payloads,
URLs and credential assignments are removed. Non-driver exceptions get a neutral
message to avoid serializing arbitrary payloads.

## Disposable PostgreSQL regression

`tests/test_daily_postgres.py` ignores DATABASE_URL completely and never relaxes
make_db's production-test guard. It accepts only a numeric localhost service
port, a fixed **test-only** account, and creates its own `izlanish_test_<UUID>`
database. Only that created database is dropped. Fixture sources/LLM responses
are synthetic and do not use API keys.

Two cases exercise raw persistence -> classifier -> candidate -> canonical
project/source/evidence -> daily publication:3 rejected,1 review,1 published,
with zero or five historical projects. Historical IDs/dates must remain intact;
source URLs contain percent encoding and JSON lists/dicts go through psycopg.
CI provisions PostgreSQL16 as a service and supplies IZLANISH_TEST_PG_PORT.

For a local disposable Docker test (no production env passed into container):

```bash
docker run --detach --name izlanish-pg-regression --publish 127.0.0.1:55432:5432 \
  --tmpfs /var/lib/postgresql/data \
  --env POSTGRES_PASSWORD=izlanish-test-only postgres:16
# Wait for pg_isready in this specific container.
docker exec izlanish-pg-regression pg_isready -U postgres
IZLANISH_TEST_PG_PORT=55432 .venv/bin/python -m pytest -q tests/test_daily_postgres.py
# Remove only the disposable test container after verification.
docker rm --force izlanish-pg-regression
```

Without a disposable service these two tests are explicitly skipped, not passed.
In this Cloud environment Docker Hub returned403 and PyPI package installation
was blocked by the network allowlist. A draft adds pypi.org/files.pythonhosted.org;
owner must publish it to permit installing a temporary native pgserver package.
The integration reproduction/fix remains pending until that prerequisite or a
Codespace disposable PostgreSQL is available. Production is not a fallback.
