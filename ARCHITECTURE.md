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

Without AI, named projects with attributed creators and concrete existence evidence can be published using extractive summaries. Uzbek descriptions, problems and audiences are copied from evidence; unsupported fields stay unknown. RU/EN input can supply narrow Uzbek structural templates with original names/quotes, not a claimed full translation. Ambiguous material remains pending with an explicit reason. A fixture analyzer exists only in tests. No sample projects are inserted into the live database. Reddit is not used in Stage 1.

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

## Discovery repair — Stage 1 (2026-10-07)
Archive backfill uses explicit inclusive calendar bounds, separate per-year runs and public, bounded source archive pagination/sitemaps plus targeted multilingual search. Publication dates are verified on articles; sitemap lastmod never becomes published_at. Discovery queues URLs durably before processing, preserving backlog and provenance. Pending archive records retain their scope and can be translated later even during a fresh run. Projects are append/merge only; first_seen is discovery time, year filters use original publication date.

Early topic filtering operates before paid analysis, with concrete product evidence taking precedence over broad noise keywords. A versioned deterministic extractor recognizes attributed named projects across Uzbek/Russian/English; foreign input is presented through narrow, evidence-backed Uzbek templates, retaining original quotes. Unsupported descriptions remain unknown. AI failure leaves retryable candidates, not silent losses. Structured run diagnostics separate source/config/parser/AI/translation errors and expose rejection and origin counts. No redesign is planned.
# Temporary preview boundary — 2026-10-07

The optional `scripts/preview.sh` exposes the existing single-origin frontend/API
through an external tunnel; it does not change collectors, UI, database schema or
scheduler. SQLite stays on the originating machine. Backend restart preserves data;
machine deletion requires an independently retained backup. `backend.app.db_transfer`
exports a consistent SQLite backup including committed WAL and refuses overwrites.
`scripts/verify_deployment.py` checks routes, assets, API, filters and stored project
identity across restarts. The hourly scheduler exists only while the API process runs.
No managed cron, worker or permanent hosting was provisioned. Public HTTPS is currently
blocked by tunnel connectivity in the managed network; no successful external deployment
is claimed. Stage 1 remains unaccepted.

## Keyless extraction — 2026-10-07

Fallback processing version 5 retries rejected/event/published candidates after
extractor changes. `extraction_version` and computed `rating_method` are stored in
content JSON; no destructive schema migration is needed. Improved analyses can
correct the product name on the existing UUID while preserving historical dates and
quotes. Mandatory creator/existence gates remain independent of the analyzer.
Explicit company launches now supply creator evidence. Editorial interview series
are rejected and old matching records become hidden, never deleted.

Parser version 4 refetches cached articles: empty/truncated title metadata falls back
to the article heading; source-specific body/date/exclusion selectors keep UzHunt
recommendations out of product evidence. Official event navigation matches anchor
labels as well as URLs, remains same-domain and bounded to two index pages plus up
to five links each. It does not scrape search engines or bypass access controls.
The one-project-per-source-article uniqueness model remains unchanged; multi-product
lists need distinct product pages for complete individual ingestion.

Diagnostics expose visible keyless/AI counts, candidate languages and pending reasons.
Source origins distinguish IT Park from generic accelerators. New seed defaults use
free sources; optional Brave profiles remain available but disabled. Source health,
operator settings and historical data survive normal startup.

## Reproducibility and date presentation

`--archive` permits historical dates while collecting current listings; only `--backfill` supplies yearly traversal windows. `--force-sources` bypasses scheduling, not coverage/processing limits. Runs record `discovery_mode`, effective limits, and selected sitemap URLs. `--inspect-url` diagnoses an exact candidate URL separately from project visibility without running discovery. No evidence gates or collector selection rules changed for this diagnostic update.

The shared frontend date formatter maps numeric Gregorian components in Asia/Tashkent to explicit Uzbek month names. It avoids browser Uzbek ICU fallbacks (M03) and applies to cards, details, status/admin and archive windows. Stored timestamps and backend timezone/filter logic are unchanged.

Candidate diagnostic IDs are SHA-256 of the existing canonical URL primary key (no schema migration). CLI lists and debug exports are read-only after normal DB initialization and never instantiate Pipeline. Debug reports retain the latest run per archive window so subsequent queue-only runs do not hide collection failures. Saved source archive configuration is compared with the current seed without applying it or re-enabling disabled sources.

Legacy registry archive repair is explicit and additive: `--repair-archive-config` fills only a missing options.archive key when seed ID, canonical endpoint and collection method match. Existing archive settings (including empty), operator flags, schedule, trust and health are preserved. A yearly collection with a missing expected seed adapter fails clearly with archive_configuration_missing / NEEDS_CONFIG instead of silently collecting only the current RSS. Normal fresh collection and sources without any seed archive adapter retain their behavior. Detection, fallback and evidence thresholds are unchanged.

When an unprocessed queued URL with an explicit date path is rediscovered in its matching yearly window, its archive_scope is routed to that window. This prevents a URL first encountered on a current listing during 2022 from being stuck in 2022 when rediscovered for 2026. Article publication metadata still must pass the ordinary date gate; URL dates do not become verified timestamps. Existing sitemap sampling and processing budgets are unchanged.

## Problem-first intelligence extension — 2026-10-07

The old standalone Global stage is superseded by this product design. Uzbekistan
remains the primary region. A monthly cross-country **problem/trend scan** is a
separate analysis scope, not a Global project feed. The prior project collector,
queue, source citations, archive and stop filter remain in place.

Schema version 4 adds structured project problem-gate fields, `problems`,
`problem_evidence`, `project_problem_links`, `solution_ideas`, richer source/signal
metadata and `scheduler_checkpoints`. It adds columns and tables in place;
existing UUIDs, dates, `first_seen`, citations and visibility survive. On app
start, cached article text is conservatively checked for a source-backed problem.
If no explicit quote and affected user are available, a legacy project is marked
`PENDING/pending_problem_analysis` and receives no opportunity grade. This does
not rewrite its historical publication or falsely claim the product never existed.

Candidate types are PROJECT, PROBLEM, SOLUTION_IDEA, SIGNAL or IGNORE. Event
records remain separate. A source article may become a problem with a verbatim
Uzbek quote and stable fingerprint; repeated identical statements append evidence.
Project links require a cited problem and solution mechanism. Minor UI features
without independent pain are rejected before analysis. Source quotes and facts
are displayed separately from opportunity hypotheses. No automatic solution idea
is created from a single article.

Opportunity inputs are fifteen 1–5 criteria across problem, market, business
model and execution. Every nonempty criterion requires a reason and evidence URL.
All fifteen are required for a numeric score. The four normalized group scores
are averaged and multiplied by evidence level: 1→0.45, 2→0.60, 3→0.75,
4→0.90, 5→1.00. A≥80, B≥65, C≥50, else D. Missing problem/evidence yields
PENDING; a fatal stop reason yields REJECTED. Automated collection alone does
not claim customer interviews, payment or pilot evidence levels 4–5. The older
Foydalilik and Tasdiqlanganlik metrics remain independent.

The scheduler keeps hourly due-source discovery and its database lease. A
15-minute watchdog catches missed 08:00/23:30 Asia/Tashkent reconciliation
and due weekly local/monthly cross-country scans after restart. Checkpoint slots,
attempts and successful completions persist in SQL. Reconciliation cannot be
described as a completed scan merely because its job exists; status exposes the
last attempt and success. The monthly job currently checks only the public
Show HN signal feed; broader international problem coverage remains unverified.

The read-only API exposes a dashboard, problems/evidence/linked projects, ideas,
signals, sector counts and expanded status. The Uzbek React dashboard links to
the existing project feed/archive and dedicated intelligence views. Source seeds
grow from 24 to 64 entries. A public Show HN RSS mirror and its HN article pages
are the sole newly active international signal source; submissions are low
confidence TECHNOLOGY signals, never confirmed projects. Other new concepts
remain disabled, and startup metadata enrichment does not overwrite operator
source switches or health. Monthly scanning is currently a bounded signal
sample, not a comprehensive global trend study.

Schema version 5 changes citation uniqueness from URL alone to
`(project_id, url)`. A SQLite table rebuild preserves citation IDs and creates
`data/finder.sqlite3.pre-multisource-backup` before changing an existing DB;
PostgreSQL drops the URL-only constraint. One event article can cite multiple
named projects when each has its own attributable creation quote. Candidate
`project_ids` records the linked UUIDs. Ordinary single-project URL dedup stays
strict; shared URL matching is enabled only during event multi-extraction.

The dashboard API now returns separate latest project/problem/idea/signal groups,
and status exposes score method, evidence level and pending grade distributions.
Public cards show the five score groups with an explicit unknown marker for
criteria that lack cited evidence. Time filters on the intelligence views use
original publication dates and do not change stored timestamps.

When a previously hidden project becomes visible after reprocessing, a run
counts its first publication as `new_projects` rather than a duplicate. The
pipeline snapshots hidden UUIDs before the legacy evidence audit, which can
otherwise mark them visible before candidate processing. Source citations and
existing project UUIDs remain unchanged. Plant-clinic language is removed from
human-health sector matching, so agricultural apps stay in agritech.

For bounded yearly backfill, queued candidates are processed first when a URL
date or feed date points to the requested year; matching project-like titles
precede generic headlines. Undated material follows, then explicit dates from
other years. This is only queue order: fetched publication metadata remains the
validation source, and mismatched/undated records remain in the durable queue.
An event overview may be recognized when its title describes projects being
demonstrated and its body explicitly identifies a forum or exhibition, even if
the title omits the event-type word. This lets the ordinary event-specific
attribution gate process named products such as BITO on a direct article fetch.

## Second pass — 2026-10-08

The frontend adds a tokenized graphite/teal presentation layer after the
existing stylesheet. Dashboard API project previews include cited problem and
market group scores when present plus the stored evidence-confidence value;
unknown score groups remain null. The dashboard uses separate entity sections
and limits its preview to three projects; the feed and archive APIs are intact.

The address-specific `--process-url` CLI queues a public HTTPS URL only when
an enabled registered source owns its host. It then invokes the normal
queue-only archive pipeline, retaining fetch, robots, publication-date,
classification, evidence and dedup gates. Explicit processing does not
enable disabled sources or bypass source protection. A new extractive version
can repair a misidentified, hidden project in place while retaining UUID,
first_seen and previous evidence.

For event reports whose headline omits the forum name, a named forum in the
lead supplies a useful follow-up query. Keyless navigation prioritizes
winner/finalist index links rather than generic news links. When the article
itself identifies an event, that direct event ID outranks the ID inherited
from a follow-up queue; a stale, sole-source project event association can be
corrected without duplicating the project. Evidence and score gates remain
unchanged except for recognizing an explicit current-product statement in a
named startup interview. No automatic scoring is inferred from the redesign.

## Public publication and international discovery — 2026-10-09

Schema v6 adds `publication_status`, `publication_reason`, secondary problem
links and the original discovery URL on projects; candidates store the cheap
project-detector result and an admin review decision. Existing project IDs,
publication dates, `first_seen`, source records and evidence stay in place.
The original `visible` flag remains an evidence-gate diagnostic. Public API
queries require `publication_status=PUBLISHED` and use `published_at` for
recent and archive periods. A status can remain `REVIEW_REQUIRED` even if the
entity has passed the `VERIFIED_PROJECT` stage: review disposition and quality
progress are distinct. The quality progression is available as a computed
`lifecycle_stage`: DISCOVERED, VERIFIED_PROJECT, ANALYZED, PUBLISHED.

The pipeline first calls a low-cost detector (`PROJECT_CANDIDATE`,
`NEEDS_EXTRACTION`, `SIGNAL_ONLY`, `NON_PROJECT`). Only project candidates
enter evidence and problem-solution analysis. A cited project may have one
primary problem and secondary cited problems. An item with missing creator,
clear problem, target user, solution or publication evidence stays in review;
it does not appear in cards or detail API. Admin ACCEPT requeues the normal
pipeline. REJECT stores a typed reason. IGNORE-classified signals remain in
SQL with `intelligence_status=IGNORED` for audit, excluded from active signal
metrics.

The public frontend uses only four top-level pages and a hidden owner area.
Former direct problem, idea, signal and sector routes redirect to `/admin`;
owner routes under `/admin/*` use the same API key as their now-protected
intelligence endpoints. The public dashboard API returns only published project
previews and three simple counters; internal entity lists stay in admin data.
Stored intelligence entities are unchanged.
`ADMIN_API_KEY` protects owner APIs with constant-time header comparison;
keys stay in environment settings. `/api/public/sources` returns a small
source directory without health or queue details. The admin API reports
queue items, source yield, rejection reasons and existing scheduler status.
Public score formulas and stored evidence are unchanged; incomplete score
groups do not appear on cards. Project detail opens with problem, audience,
solution and cited facts, with deeper analysis below.

The enabled Show HN RSS collector now keeps the maker's URL as the candidate
site and HN comments URL separately as discovery provenance. Official site
content is fetched subject to existing robots/TLS/size controls. A global
site is not assigned Uzbekistan origin by keyless fallback. Primary source,
named creator, dates, problem and audience are still required before public
publication. The CLI `--only-source` constrains both collection and queued
processing for source-yield analysis without changing operator enable flags.
Uzbekistan hourly polling, weekly local problem scan and monthly global
trend scan remain separate scheduler jobs.

For an ordinary news article with a link whose anchor names the extracted
project, the collector checks at most 30 article links and fetches the
matching external page. The project's official URL is set only if that page
contains the same name; the matching page title or excerpt is stored as a
separate `official_website` evidence record. Fetch failures do not drop the original candidate.
Optional Brave corroboration uses a country-aware query; an international
candidate is no longer searched as if it originated in Uzbekistan. Neither
step bypasses the publication gates or requires a paid key.

## Catalog pipeline v3.1

`CatalogPipeline` is the active hourly and CLI project path. Source adapters
create durable `Candidate` rows; a cheap noise check precedes the structured
LLM classifier. With no AI key, generic pages remain `review_required` with
`llm_unavailable`. Deterministic automatic publication requires a positive,
reviewed `(adapter, page_type)` pair in `config/trusted_catalog_pages.json`.
The current production file has no positive pair. The classifier contract and
prompt are versioned in `backend/app/catalog.py` and
`config/prompts/catalog_classifier_v1.txt`.

`CatalogStore` writes project/source/evidence records and append-only status,
classification and attribute history fields. The source article and discovery
submission URL are distinct. `publication_status=PUBLISHED` is the public
catalog gate; `catalog_score` may be null when no defensible score exists.
`date_estimated` prevents undated entries from appearing in recent filters.
The owner catalog actions are implemented in `catalog_admin.py` and protected
API routes. Weekly Uzbekistan and monthly Global deep intelligence scans still
run through the older `Pipeline`; their internal entities stay out of public
navigation. `reports/pipeline-baseline.json` is the pre-migration inventory.
