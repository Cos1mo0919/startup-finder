# Stage 1 — Uzbekistan

## Scope and stack
This is a web application for evidenced projects connected with Uzbekistan. The UI and generated descriptions use Uzbek Latin. Global and a separate GitHub/tools section are explicitly out of scope until user approval.

- Frontend: React + TypeScript + Vite, responsive vertical feed and project detail pages.
- Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2.
- Database: SQLite (WAL); portable SQLAlchemy models and DATABASE_URL support PostgreSQL with psycopg.
- Scheduler: APScheduler hourly at minute 00, Asia/Tashkent. Database lease prevents concurrent ingestion. Run one API worker; scheduler can be disabled for separate worker deployment.
- Deployment: one container serves the built frontend and API; local Vite proxies /api.

## Data model
Project stores identity (UUID, normalized name, creator, organization, university, country, city, event, main URL, aliases, fingerprint), original publication date, first_seen/last_seen, Uzbek content, audience, category, keywords, images, evidence-linked facts and separately labeled AI analysis. Sources retain URL, publisher, published date, exact supporting quotations, trust type and retrieval time. Rating components and rationale are persisted individually. Candidate records retain bounded article content and processing state for retry when AI credentials become available. Run records retain counters, sanitized failures and duration; a lease serializes pipeline writes.

## Data flow
RSS / optional Brave Search API → bounded, robots-aware HTTPS fetch → article parser → date gate (2022 onward, reject future/unknown dates) → Uzbekistan and real-project detector → additional source discovery → evidence extraction and Uzbek analysis → deterministic scoring → conservative identity deduplication → transaction → API → browser.

Discovery prioritizes last hour, today, last 7 days and last 30 days. Older results since 2022 can be requested explicitly with archive mode. Feed membership in “Bugun O‘zbekistonda” uses first_seen in Asia/Tashkent, never original publication time. Original dates remain visible. A later source merges into the existing project and does not reset first_seen.

## Collectors and AI
Public RSS works without API keys. Brave's documented API is optional and has a replaceable search interface. A provider-compatible chat completions adapter uses AI_API_KEY (or OPENAI_API_KEY locally), configurable model and base URL. External pages are untrusted data, never instructions. Structured Pydantic output, known source URL checks and verbatim quote checks gate facts and identity fields. The analysis translates descriptions to Uzbek and preserves proper names/URLs. Missing or unsupported fields remain unknown. Generated scores are not accepted.

Without AI, only conservative, already-Uzbek articles with a named project and concrete existence evidence can be published using extractive summaries. Foreign-language/ambiguous candidates wait for AI rather than receiving fake translations. A fixture analyzer exists only in tests. No sample projects are inserted into the live database. Reddit is not used in Stage 1.

## Ranking and deduplication
Usefulness is computed from evidence-backed categorical inputs: practical benefit 0–2.5, problem addressed 0–2, audience 0–1.5, innovation 0–1.5, usability 0–1.5, source quality 0–1. Each component and explanation is stored. Unknown criteria contribute zero; this is an evidence-constrained editorial score, not a measured business outcome. Confidence uses source types, independent publishers, named creators and verifiable project links. An official status requires operator-configured source trust, not an LLM assertion.

Canonical source URLs and official project URLs give exact matches. Otherwise compare normalized project names/aliases with creator or organization and description token similarity. Similar descriptions alone or a shared creator never merge different projects. Uncertain identities remain separate rather than silently losing projects. Sources merge under a unique URL constraint.

## Safety and operation
HTTPS only, no credentials in URLs, restricted ports, public-IP/DNS checks, redirect revalidation, robots.txt policy, per-host pacing, bounded compressed/decompressed responses, timeouts, limited candidates and retryable error states. No execution of collected code, auth/CAPTCHA bypass or fabricated images. Use only source-attributed images, otherwise a labeled placeholder. Raw credentials and raw exceptions are not exposed by the API. DNS validation complements, but does not replace, deployment egress restrictions against DNS rebinding.

Read-only API and status UI; manual ingestion is a local CLI, not an unauthenticated web mutation. Default CORS is same-origin. Processes must restart after environment restoration; files and installed dependencies can persist. Tests use temporary databases and mocked external services; live source checks are reported separately.

## Implemented operational details
- The config/sources.json seed enables Spot Uzbek/Russian RSS, UzHunt, IT Park and ICT Week HTML collectors, plus four optional Brave profiles. Regional university seeds stay disabled until verified. Gazeta.uz, TUIT and SamDU retain observed access failures in notes.
- Parser v2 prefers schema.org `articleBody`, excludes unrelated sidebar headlines and retains explicit source hyperlinks. Older queued payloads are refetched when their parser version changes.
- Managed cloud proxy DNS is opt-in (`TRUSTED_EGRESS_PROXY`), limited to exact operator-configured source hosts and AI base hostname. Arbitrary unresolved hosts fail closed. TLS remains verified; robots wildcards use Protego.
- Keyless extraction accepts explicit quoted project names or named Telegram bots with past-tense creation/launch evidence. It does not synthesize a translation. Adding AI credentials also upgrades existing extractive cards through the same deduplication path.
- Exact uncommon names with very similar descriptions can merge when creator/organization is absent and no known identity conflicts. Conflicting known identities and distinct numbered products remain separate. A company homepage alone does not merge differently named products. This remains a conservative heuristic, not a guarantee of perfect entity resolution.
- Frontend is split into Home, Detail, StatusPage, shared components, labels, request hook and formatting helpers. Browser fixtures use an isolated temporary database.
- Read-only API status is public; manual collection is restricted to the local CLI. No public admin mutation endpoint or AI-executed tools exist.

## Stage 1 radar extension (implemented)
The source registry becomes authoritative in SQL: `sources` stores configured publishers/collectors, schedules, reliability and health. Legacy article citations move losslessly to `project_sources`. Versioned migrations run before ORM access, make a SQLite backup and preserve existing project IDs, evidence URLs and first_seen. Registry seed/import is explicit and does not overwrite operator changes at every startup.

Each hourly tick selects only enabled sources whose `check_frequency` (minutes) has elapsed. Priority defaults are 5→60, 4→180, 3→480, 2→1440, 1→10080 minutes. RSS, direct-page listings and search queries use adapters selected from registry configuration. Unsupported API/browser/manual configurations remain visible as requiring setup. Health updates persist per source even on failure.

Events are independently stored with source attribution, dates when explicitly supplied, provenance and follow-up schedule. Event search expands participants/winners/projects in Uzbek/Russian/English; first-party listing links provide a keyless path. Events and ecosystem signals are never published as project cards.

`project_evidence` binds a project, registry source, article URL and verbatim quote to a role (existence, launch, prototype, creator, funding, event, etc.). A deterministic evidence score and explainable detector signals feed a mandatory stop filter. Missing named creators/teams, unsupported existence, weak evidence, idea lists, speculation, spam and invalid dates hide candidates. Existing cards are re-evaluated on migration; hidden records remain available in technical status. Adding genuine evidence can restore eligibility without changing first_seen.

Projects gain primary_sector and a list of sectors; aggregate counts include only visible PROJECT records. AI-only problem severity/frequency/affected groups/solution scope and “Nega hozir muhim?” remain distinct from source facts and do not replace usefulness. The read-only admin view exposes source health, event follow-ups, rejected candidates, ecosystem signals and evidence breakdowns.

Evidence score: best supporting reliability × 0.35 (max 3.5), existence 2, identity 1.5, distinct publisher/quote groups max 1.5, evidence-role diversity max 1.5. Default feed threshold is 5 with mandatory named-creator and existence gates. The percentage is an explanatory heuristic, not a calibrated probability. Source candidates_found is the latest collection count; new_projects is cumulative. New event follow-ups run on later ticks, capped at three events per run and six-hour recurrence. Dates and organizers remain unknown without explicit evidence.

Version 2 migration has legacy preservation and repeatability tests; SQLite also creates a one-time pre-radar backup. PostgreSQL deployment/migration remains untested. Registry seed never overwrites existing operator settings implicitly; --update-sources is explicit. Source and event health distinguish missing configuration from usable sources; acquisition success is distinct from acceptance of a project.
