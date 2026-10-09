# Public catalog and Global discovery validation — 2026-10-09

This report covers the current local SQLite checkout. The database is ignored by
Git and is not transferred to another Codespace by the code commit.

## Data and publication

Before the change, the database had 15 project rows, 1,109 candidates, 15
project-source links and 56 project evidence records. A consistent SQLite
backup was saved at `/tmp/izlanish-before-global-transition.sqlite3` before
the schema update. Afterwards, all 15 original project IDs and their
`first_seen` and publication timestamps matched the backup. The source count
remained 15; evidence rose from 56 to 57 after KotibAI's named official page
was checked and its verbatim title stored. Candidate records grew to 1,136.
No historical project was deleted.

Current project states: 15 records; 7 pass the earlier existence/evidence
visibility check, 2 also pass the new complete public analysis check, 11
require review, and 2 fail a fatal gate. The 2 public records are DMED
(2025-01-07, source: `https://www.spot.uz/oz/2025/01/07/dmed`) and KotibAI
(2026-03-10, source: `https://www.spot.uz/oz/2026/03/10/kotibai`). A later
idempotent recheck verified the article's project-named link
`https://kotib.ai/` against the product page and stored it as KotibAI's
official URL. DMED has no separately verified official product URL in this
database. The Spot source remains identified as an article. Their cited problems are
prescription-creation errors and the time journalists spend transcribing an
interview. The prior other five existence-verified cards stay in SQL and
review; their problem/solution evidence is insufficient for the requested
public card hierarchy. They were not erased or falsely graded as strong.

The public project API, home, catalog and archive all use the same `PUBLISHED`
gate. Today's new-project count uses the source publication date; the two
public projects are historical and count as archive items. A startup article
discovered today with a 2023 publication date cannot become a new project.
The catalog uses a simple country choice; international records have an
explicit `International` country if the evidence does not identify one.
Repeated legacy usefulness scores were inspected: several 2.1 values come
from the same supported rubric components (described product 0.5, available
use 1.0, media source 0.6; unknown problem/audience/innovation contribute
zero). They are not cached values copied between records. The unfinished
opportunity score remains `PENDING`; no grade or average was raised to make
public cards look better.

## Discovery passes

No AI or paid search key was configured. The source registry had 64 records,
12 enabled. The enabled Show HN RSS source was corrected to collect external
maker links and retain the HN comments URL separately. A source-restricted
CLI command processed its backlog without being displaced by older local
queue items. Robots, TLS, source enable flags, dates, attribution and evidence
gates remained active.

Two real source-restricted runs were completed:

| Run | Source checks | Links discovered | Candidates processed | Rejected | Pending | Newly published | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 63, Show HN | 1 | 29 | 20 | 10 | 7 | 0 | 3 page fetch/parse errors |
| 64, Spot Startups | 1 | 29 | 6 | 3 | 2 | 0 | 0 |

Two URL-specific rechecks (runs 65–66) processed the stored KotibAI
candidate and completed with 1 existing-project match each, 0 new projects
and 0 errors. They added the verified product URL and the product page's
verbatim title as separate evidence while retaining project ID, first-seen
timestamp and publication date.

Show HN's 20 processed source items included 7 detector-level project
candidates. None had sufficient verified creator, publication date, problem
and Uzbek source-backed solution text to pass the full pipeline. Seven remain
pending (mostly `missing_creator`), 8 were `not_project`, 2 had an old
publication date, 1 page returned 503 and 2 pages lacked readable article
content. No site protection was bypassed. Spot Startups yielded 2 project
candidates among 21 durable candidate records from that source; its targeted
run found no new complete project. The run rejected 2 `not_project` items and
1 with unknown publication date; 2 stayed pending. A separate broad run
processed older local backlog and did not publish a new card. These are
bounded samples, not claims of complete Uzbekistan or Global coverage.

Source-yield snapshot (the fetched count is the source registry's **last
check**, while candidate and outcome counts are **durable totals**):

| Source | Last fetched | Candidate records | Detector project candidates | Earlier evidence-verified | Public | Current rejected | Main reason |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Spot Uzbek RSS | 56 | 443 | 2 | 7 | 2 | 227 | `not_project` 210 |
| Spot Startups | 20 | 21 | 2 | 1 | 0 | 12 | `not_project` 9 |
| IT Park | 16 | 40 | 3 | 0 | 0 | 21 | `noise_topic` 18 |
| UzHunt | 6 | 6 | 0 | 0 | 0 | 5 | `outside_archive_window` 5 |
| Show HN | 20 | 20 | 7 | 0 | 0 | 10 | `not_project` 8 |

Current candidate states after audit: 206 queued, 271 pending, 5 requiring
review, 609 rejected, 17 errors, 19 event records, 6 ecosystem candidate
records, 1 standalone problem and 2 publicly published candidate records.
The original signals remain in SQL. Of 6 stored ecosystem signals, 2 generic
education/tax notices were marked `IGNORED`; 4 remain active for internal
intelligence. The total distribution is not a single-run funnel.

Current rejection diagnostics include `not_project` 520, `noise_topic` 46,
`outside_archive_window` 19, `unknown_publication_date` 19,
`parser_failure` 15, `old_date` 5 and `blocked_source` 2. Duplicate counts
are cumulative run events (11, including the two KotibAI rechecks), not 11
newly created duplicate projects.

## Validation and limits

The full backend suite, Ruff, frontend TypeScript/Vite production
build and 10 desktop/mobile browser checks ran with isolated test databases. Tests cover
project detection, incomplete-publication hiding, review actions, date/archive
semantics, source provenance, global country handling, signal cleanup, public
navigation and admin access. See the final project status for exact pass counts.

The review UI requeues ACCEPT through normal validation; it does not grant
publication. `ADMIN_API_KEY` is required in environment settings to use
`/admin`, `/api/admin/*` and the internal problem, idea, signal and sector APIs.
Legacy direct intelligence page links redirect to `/admin`; the same views are
available after owner sign-in under `/admin/*`. When the key is absent, the
admin API is intentionally unavailable. The public dashboard API includes only
published project previews and its three displayed counters. The current keyless global feed is useful for candidate discovery
but produced **zero published Global projects** in this bounded pass. No
unverified company, founder, date, translation or customer claim was added
to increase yield. Other international directory seeds remain disabled until
their access, robots and parsers are validated. Public HTTPS deployment was
outside this task; the browser checks were local.
