---
name: izlanish-discovery-operations
description: >
  Operational discovery rules for the izlanish / startup-finder project.
  Use this skill whenever modifying source registry, schedulers, source polling,
  backfill, event discovery, queues, retries, source health, archive recovery,
  continuous daily scanning, weekly Uzbekistan-local problem discovery,
  monthly global scans, or any logic that controls how new data is discovered,
  processed, retried, resumed, or persisted.
---

# izlanish Discovery Operations

## Current catalog workflow — v3.1

Follow `docs/PROJECT_CATALOG_PIPELINE_V3_1.md` for catalog discovery.
Generic keyless RSS/news stays `REVIEW_REQUIRED` with `llm_unavailable`;
only explicit repository allowlisted `adapter + page_type` pairs may publish
deterministically after meaningful extraction and deduplication. Maintain an
idempotent enrichment queue for deterministic publications when LLM access
later appears. Preserve excerpts and status/classification histories. An old
project found today remains in its publication-date archive. Uzbekistan and
Global project discovery continue together.

## Purpose

This skill defines how the izlanish / startup-finder system discovers, queues,
retries, processes and preserves information.

This skill does NOT define what a good startup is.
That belongs to product-intelligence logic.

This skill defines:

- where data comes from;
- how often sources are checked;
- how candidates enter the system;
- how queued items are processed;
- how failed sources are retried;
- how archive/backfill works;
- how the system resumes after restart;
- how source health is monitored;
- how daily, weekly and monthly discovery differs.

The main principle is:

**Discovery must be continuous, recoverable, observable and non-destructive.**

---

# 1. Core Operational Pipeline

The operational pipeline should be:

SOURCE REGISTRY
→ SOURCE SCHEDULE
→ FETCH
→ NORMALIZE
→ CANDIDATE EXTRACTION
→ QUEUE
→ CLASSIFICATION / ANALYSIS
→ DEDUP
→ PERSIST
→ STATUS / METRICS

A source fetch failure must not destroy the entire run.

A single parser failure must not block other sources.

A queued candidate must have a clear lifecycle.

---

# 2. Continuous Daily Discovery

The system must discover useful data throughout every day.

Do NOT rely only on fixed publication windows.

High-priority sources should be checked repeatedly during the day.

Recommended general policy:

Priority 5:
approximately every 1 hour

Priority 4:
multiple times per day

Priority 3:
daily or several times per day depending on source

Priority 2:
less frequently

Priority 1:
manual / occasional / low-frequency

Actual scheduling must be controlled by source registry configuration.

The same global rule should not be forced onto every source.

---

# 3. Reconciliation Passes

Keep two daily reconciliation passes:

08:00 Asia/Tashkent

23:30 Asia/Tashkent

These are NOT the only times the system may publish.

Their purpose is:

08:00
- catch overnight items;
- retry temporary failures;
- process remaining queue;
- discover missed high-priority content.

23:30
- process remaining daily backlog;
- retry failed pages;
- reduce queue;
- ensure important candidates were not skipped.

If the server was offline at exactly 08:00 or 23:30,
the system must recover later.

Do not create data gaps because a scheduled minute was missed.

---

# 4. Weekly Uzbekistan Local Problem Scan

Run a dedicated deep problem-discovery process approximately once per week.

This process is specifically for:

UZBEKISTAN_LOCAL problems

Examples:

- regulation;
- local tax/accounting;
- labeling/compliance;
- public services;
- payments;
- logistics;
- local infrastructure;
- regional service gaps;
- language;
- local business workflows.

This weekly scan is separate from normal project discovery.

Uzbekistan projects should still be discovered daily.

Weekly scan means:
deep local problem intelligence,
not weekly project updates.

---

# 5. Monthly Global Scan

Run a deeper global intelligence scan approximately once per month.

Purpose:

- global problems;
- market shifts;
- technology trends;
- repeated international startup patterns;
- global opportunity signals;
- growing categories;
- emerging business models.

Do not mix monthly global scanning with ordinary daily source fetching.

Daily discovery may still find international projects and everyday problems.

Monthly scan is deeper trend analysis.

---

# 6. Source Registry

The source registry is a core operational component.

Every source should have fields similar to:

id
name
url
source_type
region
country
sector
purpose
collection_method
priority
configured_frequency
reliability_score
enabled
parser_type
last_checked_at
last_success_at
last_error_at
last_error_message
consecutive_failures
created_at
updated_at

Optional useful fields:

supports_projects
supports_problems
supports_signals
supports_events
supports_rss
supports_archive
requires_javascript
requires_auth
notes

The registry must be database-backed or otherwise persistent.

Do not hard-code all source behavior in one large scheduler function.

---

# 7. Source Health

Track source health continuously.

Suggested states:

HEALTHY
DEGRADED
FAILING
DISABLED
UNKNOWN

Useful indicators:

- HTTP status;
- last success;
- last failure;
- failure streak;
- parse success rate;
- items found;
- candidate yield;
- average latency;
- last schema/parser error.

A source returning 403/503 temporarily should not immediately be deleted.

Use retries/backoff.

If a source repeatedly fails, mark degraded or failing.

Expose this in status/admin.

---

# 8. Retry Policy

Retries must be controlled.

Use exponential or bounded backoff.

Avoid tight retry loops.

Suggested behavior:

temporary network failure
→ retry later

429
→ respect rate limits / backoff

403
→ do not spam retries; mark source issue

404
→ inspect whether URL changed

5xx
→ retry with bounded policy

parser failure
→ store diagnostics

One failing source must not fail the entire discovery run.

---

# 9. Queue Lifecycle

Every candidate should have a clear state.

Suggested states:

QUEUED
PROCESSING
PENDING
PUBLISHED
REJECTED
DUPLICATE
FAILED
IGNORED

Queue records should store:

created_at
updated_at
attempt_count
last_attempt_at
next_attempt_at
failure_reason
source_id
candidate_url
candidate_date
priority

Avoid permanent QUEUED states.

A queue should progress over repeated drain cycles.

If a candidate cannot progress,
store the exact reason.

---

# 10. Queue Draining

Repeated drain operations must reduce actionable backlog.

A drain command should:

- process queued items;
- retry eligible pending items;
- skip items still under backoff;
- stop safely at configured budget;
- preserve remaining queue;
- report counts.

Never silently discard queued candidates because budget is exhausted.

A limited run may leave items queued.

That is acceptable.

But repeated runs must not endlessly revisit the same broken state without diagnosis.

---

# 11. Budgeting

Discovery and processing should support budgets.

Examples:

MAX_CANDIDATES
ARCHIVE_PAGES
MAX_SOURCES
MAX_FETCH_TIME

Budgets protect against:

- runaway scraping;
- infinite archive loops;
- excessive processing;
- usage spikes.

But budget limits must be visible in diagnostics.

If 1,000 candidates remain queued,
the status/report should make that clear.

Do not confuse:
“not processed yet”
with
“rejected”.

---

# 12. Persistence and Recovery

Discovery state must survive process restarts.

Persist:

last successful scan
last source check
last processed item
queue
retry schedule
archive cursor
page cursor where applicable
source health
backfill progress

After restart:

continue from stored state.

Do not restart archive scanning from scratch unless explicitly requested.

Do not lose first_seen.

---

# 13. last_successful_scan_at

Use checkpoint fields such as:

last_successful_scan_at
last_successful_source_check_at
last_processed_item_at

These should prevent data loss.

If server is offline for six hours,
next run should resume from the last successful point.

Do not define discovery strictly as:

“only articles published since current midnight”

because that can create gaps.

Use durable checkpoints plus publication dates.

---

# 14. Archive / Backfill

Historical backfill is separate from fresh discovery.

Backfill must:

- preserve current database;
- add new evidence;
- deduplicate;
- keep first_seen;
- support progress continuation;
- use configurable date ranges;
- use page/candidate budgets;
- produce reports.

Current required Uzbekistan backfill support:

2022-01-01
through
2026-09-30

Do not require deleting the database.

Do not fake completeness.

If backfill is limited by page budget,
report remaining work.

---

# 15. Fresh Discovery vs Archive

Keep these concepts separate.

Fresh discovery:
recent content / ongoing daily operation.

Archive/backfill:
historical content.

A source may support both.

Do not let archive rules accidentally prevent fresh items from being processed.

Do not let an old archive window incorrectly bind a new candidate to the wrong year.

Candidate date logic must use real publication evidence where possible.

---

# 16. Date Handling

Candidate dates may come from:

- article publication date;
- event date;
- structured metadata;
- URL;
- page text;
- source feed.

Prefer explicit publication metadata.

Use URL dates only as a hint.

Never accept URL year as stronger evidence than a real article date if they conflict.

Store:

publication_date
discovered_at
first_seen_at

These are different concepts.

---

# 17. Event Discovery

Event discovery is a special operational workflow.

When an event is found:

EVENT PAGE
→ PARTICIPANT LIST
→ FINALISTS
→ WINNERS
→ PROJECT NAMES
→ CREATOR NAMES
→ PROJECT PAGES
→ EVIDENCE

Do not stop at event article extraction.

One event page may contain multiple projects.

Support multiple-project extraction when possible.

Preserve the relationship:

event
→ project

---

# 18. Multi-Project Pages

Do not assume one page equals one project.

List pages may contain:

- 10 startups;
- finalists;
- award winners;
- university teams;
- demo-day projects.

Extract multiple candidates safely.

Each candidate should preserve:

source page
section/context
name
creator
event
linked URL if available

---

# 19. Source-Specific Collection Methods

Source registry may define:

RSS
HTML
API
JSON
SITEMAP
TELEGRAM
SEARCH
MANUAL
EVENT_CRAWL

Prefer stable structured methods over fragile scraping.

Preference order when available:

API / RSS / JSON
then
structured HTML
then
generic HTML parsing
then
manual fallback

Avoid browser automation unless needed.

---

# 20. Free / Keyless Mode

Discovery must remain useful without paid search or AI APIs.

Prefer:

RSS
public HTML
public APIs
sitemaps
direct event pages
deterministic extraction

Paid APIs may enhance coverage.

They must not be required for basic operation.

If optional API keys are absent:
degrade gracefully.

---

# 21. Source Integration Strategy

Do not integrate every possible source at once.

Prefer a stable active core.

A reasonable early operational set:

20–30 reliable sources

Then expand.

Unstable sources may remain:

REGISTERED
but
DISABLED

or:

PENDING_INTEGRATION

Do not remove them from the source registry merely because parser work is incomplete.

---

# 22. Source Priority

Priority should influence:

- check frequency;
- processing order;
- retry urgency;
- queue order;
- reconciliation behavior.

Example:

Priority 5:
official/high-value local sources

Priority 4:
strong regional/startup sources

Priority 3:
useful secondary sources

Priority 2:
low-frequency supplemental sources

Priority 1:
experimental/manual sources

Do not confuse source priority with evidence strength.

An official project page may have strong evidence even if source polling priority is low.

---

# 23. Candidate Priority

Candidates may also have priority.

Useful signals:

- official source;
- local relevance;
- strong project language;
- event finalist/winner;
- direct product page;
- multiple source matches;
- strong problem evidence.

Candidate priority may control queue processing order.

But priority must not bypass quality filters.

---

# 24. Dedup Before Expensive Analysis

When possible:

normalize URL/name
→ check exact duplicates
→ check known project aliases
→ then perform expensive AI/semantic analysis

This saves cost and processing time.

Do not repeatedly analyze obvious duplicates.

---

# 25. Source Failure Isolation

If one source fails:

continue processing other sources.

If one page fails:

continue processing other pages.

If one candidate fails:

continue processing other candidates.

Every failure should be recorded with enough context for debugging.

Never wrap an entire run in one fragile transaction if that causes all progress to roll back.

---

# 26. Idempotency

Repeated runs must be safe.

Running the same source twice should not create duplicate projects.

Running the same backfill twice should not create duplicate entities.

Running queue drain twice should not duplicate processed evidence.

Use stable dedup keys and idempotent writes.

---

# 27. Observability

Every discovery run should produce structured metrics.

Suggested metrics:

sources_checked
sources_successful
sources_failed
pages_fetched
candidates_created
candidates_queued
candidates_processed
published
pending
rejected
ignored
duplicates
problems_created
projects_created
signals_created
ideas_created
events_found
parse_errors
network_errors
remaining_queue

Reports should clearly distinguish:

newly created
updated
existing
queued
rejected

---

# 28. Status/Admin

The status page should expose:

scheduler state
last run
next run
current queue
source health
failure streaks
candidate backlog
archive progress
weekly scan status
monthly scan status
reconciliation status

Per-source:

name
enabled
priority
last check
last success
health
items found
candidates generated
errors
last error

This should be operationally useful.

---

# 29. Scheduler Safety

Scheduler tasks must not overlap destructively.

If a previous heavy run is still active,
avoid launching another identical run unless concurrency is explicitly safe.

Use locks or run-state tracking.

Different tasks may coexist if designed safely.

Examples:

fresh discovery
weekly problem scan
backfill

must not corrupt each other.

---

# 30. Timezone

Operational timezone:

Asia/Tashkent

Store timestamps safely, preferably UTC internally where practical.

Scheduler rules should resolve correctly in Asia/Tashkent.

User-visible timestamps should be localized.

---

# 31. Data Preservation

Never delete historical records merely to “refresh” a source.

Updates should be additive or corrective.

Preserve:

first_seen
source history
old evidence
project aliases
problem aliases
run history where useful

If a source article disappears later,
do not automatically delete the entity.

Mark source availability separately.

---

# 32. Manual Repair Tools

Operational tools may support:

repair archive config
reprocess candidate
inspect URL
inspect candidate
retry source
re-score
drain queue
backfill range

These should be safe and idempotent.

Avoid destructive repair commands by default.

---

# 33. Diagnostics

When something is stuck,
the system should answer:

Why is this queued?

Why is this pending?

Why was this rejected?

Why did this source fail?

Why is archive incomplete?

Why did this candidate not publish?

Avoid generic statuses without reasons.

---

# 34. Tests Required

Whenever modifying discovery operations,
add/update tests for relevant behavior.

Important coverage includes:

source failure isolation
retry behavior
queue progress
idempotency
archive resume
scheduler resume after restart
priority scheduling
daily reconciliation
weekly Uzbekistan-local scan
monthly global scan
date parsing
wrong-year protection
multi-project pages
event discovery
source health
budget exhaustion
queue diagnostics
keyless operation

---

# 35. What This Skill Must Be Used For

Use this skill whenever modifying:

- source registry;
- source polling;
- scheduler;
- source frequency;
- source priority;
- retries;
- queue lifecycle;
- drain logic;
- archive/backfill;
- event discovery;
- multi-project extraction;
- source health;
- persistence/recovery;
- run reports;
- status diagnostics;
- continuous daily discovery;
- weekly local problem scan;
- monthly global scan;
- source failure handling.

Do not use this skill as the primary authority for:

- product classification;
- problem-quality logic;
- scoring;
- UI appearance;
- CSS;
- business opportunity grades.

Use the specialized skills for those.

---

# 36. Non-Negotiable Rules

Never:

- lose queued candidates silently;
- reset historical data on restart;
- delete first_seen;
- let one failing source kill the whole run;
- create duplicates on repeated runs;
- confuse processing-budget exhaustion with rejection;
- leave items queued forever without reason;
- assume one page always contains one project;
- depend on paid APIs for basic operation.

Always:

- persist progress;
- expose backlog;
- retry safely;
- preserve archive;
- isolate failures;
- make repeated runs idempotent;
- record diagnostics;
- recover after restart.

---

# 37. Core Principle

The defining operational principle is:

**Discovery must continue safely over time without losing history, duplicating data or depending on one perfect run.**

A healthy system should tolerate:

- restarts;
- source failures;
- partial runs;
- archive budgets;
- temporary network errors;
- missing AI/search APIs;

and continue making forward progress.
