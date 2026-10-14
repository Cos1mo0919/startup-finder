# Render Docker Web Service

Deployment branch: `render-deploy`, based directly on GitHub `main` at
`fcba079`. It contains PostgreSQL/migration/merge code and tests, not the
`migration-data` branch history. No databases, backups or data reports are in
the branch's current tree or Docker build context. Historical reports inherited
from main are removed from this tree; main's Git history is not rewritten.

## Service

Create a Render **Web Service**, connect the private repository, choose branch
`render-deploy` and Docker runtime. Dockerfile: `./Dockerfile`; context: `.`;
health endpoint: `/api/health`. Keep the Docker default command. `render.yaml`
provides the equivalent Blueprint with a Starter service and one instance.
No service has been created by Codex and no production database has been used.

The multi-stage Dockerfile runs `npm ci` and `npm run build` with Node 24,
then copies `frontend/dist` into the Python runtime. FastAPI serves `/assets`
and the SPA routes. The entrypoint uses `exec uvicorn`, binds `0.0.0.0` and
reads Render's `PORT`; health checks use the same port. One worker is intentional.
Persistent records live in external PostgreSQL, never Render's ephemeral disk.

## Environment variables

| Name | Purpose |
|---|---|
| `DATABASE_URL` | Required server-side PostgreSQL connection; Supabase Session pooler, TLS enabled. Plain `postgres://` and `postgresql://` use psycopg. |
| `ADMIN_API_KEY` | Required for owner/admin access; generate and store in Render secrets. |
| `PORT` | Supplied by Render; no fixed port override needed. |
| `SCHEDULER_ENABLED` | Enable/disable all integrated background jobs. |
| `DATABASE_AUTO_MIGRATE` | Enable/disable schema migration and DB identity/lease bootstrap during web startup. |
| `STARTUP_DATA_UPDATES_ENABLED` | Enable/disable source seeding, historical audits, problem migration and publication synchronization during web startup. |
| `CORS_ORIGINS` | Optional JSON array of exact API client origins. Empty by default. |
| `LLM_ENABLED`, `LLM_PROVIDER_ORDER` | Optional AI processing controls. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Optional Gemini configuration. |
| `GROQ_API_KEY`, `GROQ_MODEL` | Optional Groq configuration. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Optional OpenRouter configuration. |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Optional OpenAI configuration. |
| `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` | Existing optional compatibility configuration. |
| `SEARCH_API_KEY` | Optional Brave Search API. |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` | Optional Telethon ingestion; credentials/session must be protected. |
| `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_CHAT_ID` | Optional exception-only admin alerts. |
| `USER_AGENT`, `FETCH_TIMEOUT`, `MAX_CANDIDATES`, `ARCHIVE_PAGES` | Existing optional collection settings. |

No secret is embedded in the frontend or image. No `VITE_*` secret variables
are required. Model defaults are kept from main; choose supported models in
the platform settings as needed. Provider pricing and quotas are external.

## Safe initial deployment and schema

The Blueprint sets `SCHEDULER_ENABLED=false`, `DATABASE_AUTO_MIGRATE=false`,
`STARTUP_DATA_UPDATES_ENABLED=false`. This disables background jobs and web
startup writes. An initialized schema, including RLS, is required: the web
service checks tables/columns/RLS and fails clearly when preparation is missing.
It never silently creates a local SQLite database. Tests use explicit temporary
SQLite and are protected from production PostgreSQL.

Schema preparation is a **separate explicit operator action**, after taking a
backup and stopping writers, using the same deployment code and DATABASE_URL:

```bash
.venv/bin/python -m backend.app.schema
```

Run from Codespace or a one-off maintenance process. This command creates/
updates the schema and ensures RLS; it does not run discovery or import any
backup. Existing versioned data migrations may backfill historical counters
when applicable. Review it before executing against a live database. Codex has
not executed this command against production. No automatic Render pre-deploy
command is configured. Then start the web service with the three flags still off.

The PostgreSQL security step is idempotent and covers all 22 application tables,
including `schema_migrations`: `ENABLE ROW LEVEL SECURITY` and revocation of
table privileges from `PUBLIC` and, when present, Supabase `anon`/`authenticated`.
It creates no permissive policies. Backend DATABASE_URL must use the table owner
or a BYPASSRLS role, never `anon`/`authenticated`. The browser talks to FastAPI,
not directly to Supabase REST. Owner/BYPASSRLS backend access remains available;
FORCE RLS is not enabled. The schema-readiness check detects an incompatible
backend role. The security step does not delete or rewrite project records.

## API and CORS

Frontend requests use relative `/api/...` URLs: the Render HTTPS origin serves
both frontend and backend. No CORS configuration is required for this setup.
Vite's development proxy is development-only and is not used by the image.
For a separate API client origin, configure `CORS_ORIGINS` as a JSON array of
exact origins, for example `["https://client.example"]`; credentials are not
enabled and the admin header remains required. The shipped frontend continues
to use its own origin; this setting does not redirect its requests elsewhere.

## Background jobs

When enabled, the existing scheduler registers:

| Job | Frequency |
|---|---|
| Due-source discovery | Hourly, minute 00, Asia/Tashkent |
| Daily queue processing | Daily at SCHEDULER_HOUR (default 09:00 Asia/Tashkent) |
| Raw queue processing | Every 15 minutes |
| Catalog reanalysis | Every 6 hours |
| Telegram ingestion | Every 15 minutes; needs credentials |
| Admin exception alerts | Every 30 minutes; needs bot configuration |
| Deep analysis | Every 4 hours |
| Reconciliation watchdog | Every 15 minutes and on scheduler start |

The watchdog handles daily 08:00/23:30 reconciliation, weekly Uzbekistan-local
problem scans and monthly Global trend scans. `SCHEDULER_ENABLED=false` prevents
all these jobs from running. It does not disable explicitly invoked CLI commands.
Backfill/merge never runs automatically on deployment. Web shutdown waits for
running scheduler jobs. Keep one Render instance/worker while scheduler lives in
the web service; an always-on paid service is recommended. A sleeping/free web
service cannot provide reliable hourly execution. A separate worker/cron would
be needed for that deployment; none is provisioned by this branch.

After initial verification, the owner may enable the scheduler deliberately.
Leave startup data updates off unless audits/seeding are explicitly desired.

## Merge tools

`backend.app.merge_dry_run`, `backend.app.merge_execute`, SQLite export/restore
and verification tools are included as code. Input databases, approved plans,
decisions and restore reports are deliberately absent. Supply them privately
from a backup location when needed; they are not build artifacts. Do not run
the merge from Docker startup. The executor defaults to rollback; explicit
apply requires approved inputs, successful restore proof, stopped writers and
matching baseline, with locks and count/value checks in one transaction.

## Update and validate

Push code to `render-deploy` and use Render Manual Deploy for the selected commit
(or deliberately enable auto-deploys). Logs are under the service's Logs tab;
restart via Manual Deploy / Restart service. Secrets stay in Environment.
Verify `/api/health`, `/`, `/loyihalar`, `/arxiv`, a project detail and admin
status. Confirm `scheduler_enabled=false` initially; after opting in, monitor
next run/source last checks in `/api/admin/status` using the admin header.

Local checks: backend pytest, Ruff, TypeScript/production build and Playwright
all use temporary SQLite. Docker build was attempted in Codex but Docker Hub
returned 403 for the base image; a full image build and actual PostgreSQL RLS
migration must still be verified in Render/Codespace. No production operations
were run during preparation.
