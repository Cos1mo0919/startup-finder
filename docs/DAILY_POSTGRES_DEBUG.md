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

## Run113: autocommit/ACTIVE evidence and fix

The new driver message identifies an autocommit setter failure. No application
publication code explicitly assigned autocommit; the runtime engine enabled
`pool_pre_ping=True`. SQLAlchemy's installed `PGDialect_psycopg.do_ping()` reads
old autocommit, sets it True, executes SELECT1, and restores it in finally.
Either setter can fail on ACTIVE. `free_daily` additionally installed SIGALRM
which could interrupt psycopg mid-command; restoring autocommit could then mask
the deadline exception. The exact timing of run113 was not replayed against
production, and production was not accessed.

Changes:

- `connection_pool.runtime_engine`, used by `make_db`, disables PostgreSQL's
  autocommit-toggling pre-ping and supplies a checkout probe without changing
  isolation/autocommit. SQLite retains its previous pre-ping/PRAGMA handling.
- IDLE is probed with SELECT1 followed by rollback before application borrowing.
  INTRANS/INERROR are rolled back first. ACTIVE/UNKNOWN/closed connections are
  discarded through SQLAlchemy DisconnectionError and replaced; rollback is
  never attempted on a socket with a command in flight. Interrupted probes are
  explicitly invalidated. Pool reset-on-return remains rollback.
- SIGALRM/setitimer removed from daily processing: the monotonic deadline is
  checked between operations. Daily CLI sets a30-second PostgreSQL statement
  timeout on each FRESH connection (SET followed by commit before user work)
  and10-second connect timeout. No existing publication transaction is committed
  to change settings. HTTP/LLM already have bounded timeouts. The45-minute limit
  is cooperative: one in-flight bounded operation/cleanup can finish after it;
  the Actions job retains its48-minute hard timeout.
- Catalog and legacy pipeline releases execute in a dedicated last finally
  transaction, even if Run creation/report persistence fails. Outer daily writer
  already owns its own finally; close errors now cannot skip ACTIVE context reset
  or reporting. Failed publication transactions roll back via factory.begin().
  If PostgreSQL is unreachable or the process is forcibly killed, an immediate
  release cannot be guaranteed; durable lease expiry remains the recovery path.

Other audit hits are not runtime autocommit changes: migration_recovery and
sqlite_postgres_migration issue SET TRANSACTION only in explicit maintenance
commands. The disposable test fixture selects AUTOCOMMIT at engine creation for
CREATE/DROP DATABASE only, on localhost. No VACUUM or CREATE INDEX CONCURRENTLY
is invoked by daily/catalog processing. No dynamic runtime isolation-level change
remains in this application's collection/publication path.

`tests/test_connection_hygiene.py` reproduces the EXACT message by executing the
original installed SQLAlchemy do_ping against an ACTIVE driver double, then
checks the safe checkout, invalidation, rollback and releases on report/close
failures. This is an executed offline reproduction, not a live PostgreSQL claim.

Separate workflow `.github/workflows/postgres-regression.yml` provisions a
PostgreSQL16 service, needs NO repository secrets and runs only on its own
localhost UUID databases. It is workflow_dispatch / pull_request, not a production
cron. It runs5 PostgreSQL cases:2 general catalog scenarios; original do_ping on
a real libpq ACTIVE socket; review->publication with an ACTIVE returned socket;
and the same path with failure after INSERT, rollback, release and successful
retry. These5 cases remain explicitly skipped when no local PostgreSQL service
is supplied. CI service failure fails the job rather than silently skipping.

Local checks after this fix:392 backend tests passed,5 PostgreSQL tests skipped;
Ruff, TypeScript/Vite and22 browser tests passed. Actual PostgreSQL execution and
Supabase trial remain unverified in this Cloud environment. No schema migrations
or production writes were performed.
