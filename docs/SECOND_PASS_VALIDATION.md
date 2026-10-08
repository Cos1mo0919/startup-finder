# Stage 1 second pass — 08.10.2026

This pass changed the visual identity and ran bounded, keyless discovery on the
existing Cloud SQLite database. It did not reset that database. AI and Search
keys were explicitly empty. Counts below describe this workspace, not a
complete archive or a user's separate Codespace.

## Visual review

- The site uses graphite, layered teal radial light, three surface levels and
  shared color tokens. The home page is an intelligence overview with distinct
  opportunities, projects, problems, ideas and signals sections. Only three
  latest projects appear on the overview; the full feed remains at `/loyihalar`.
- Project cards lead with the actual problem and audience, then opportunity and
  compact scores. Unknown scores remain `—` or `Dalil kutilmoqda`. No example
  metrics or generated ideas were inserted.
- Status distinguishes run, queue and source health. When the scheduler is
  disabled, it explicitly says so. Desktop 1440 px, tablet 820 px and mobile
  390 px were inspected in Chromium; none had horizontal overflow.

## Keyless discovery and preservation

Before: 13 project rows / 5 visible, 3 problems, 3 signals, 906 candidates.
A consistent pre-run SQLite backup is at
`/tmp/izlanish-before-second-pass.sqlite3` (not committed).

| Operation | Source checks | Links reported | Processed | New visible | Rejected decisions | Pending decisions | Duplicates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Forced current listings | 12 | 159 | 60 | 0 | 53 | 5 | 0 |
| 2024 archive window | 12 | 268 | 40 | 0 | 0 | 40 | 0 |
| 2025 archive window | 12 | 286 | 40 | 0 | 0 | 40 | 0 |
| One archive queue drain | 0 | 0 | 40 | 0 | 16 | 20 | 0 |

The same 12 enabled sources were checked in each collection pass; 24 annual
checks are repeated checks, not 24 distinct sources. All 12 source collections
succeeded. The forced run reported two event follow-up network errors, and the
drain reported two `article_body_missing` errors. Each run was `partial` because
of remaining pending work or those errors, not a source-wide failure. There were
no AI calls and no Search API results. The 713 reported links across the three
collection passes can repeat; they are not 713 unique candidates.

`--process-url` now permits a single HTTPS article from an enabled registered
source to be fetched and processed using the ordinary safety, date, attribution,
deduplication and stop filters. It never creates a project directly. This was
used for a linked Spot article that the bounded source listing had not reached.

| Newly published project | Creator | Publication date | Project evidence | Source | Legacy Foydalilik / Tasdiqlanganlik |
| --- | --- | --- | --- | --- | --- |
| Tahrirchi | Muhammadsaid Mamasaidov | 29.06.2023 | The interview identifies the founder and an existing Uzbek spelling and transliteration product. A mixed-quote ad label initially caused an incorrect hidden name; reprocessing corrected the same new UUID. | https://www.spot.uz/oz/2023/06/29/tahrirchi | 1.1 / 6.72 |
| Tilmoch | Muhammadsaid Mamasaidov | 12.09.2025 | Spot names the founder, describes a live translation platform and cites product launch and awards. Its usage figures remain attributed to Spot, not independently verified. | https://www.spot.uz/oz/2025/09/12/tilmoch | 2.1 / 7.32 |

Both cards passed the publication stop filter: a dated source, attributed
founder and evidence of an existing product were present. The affected user
and underlying problem were **not sufficiently evidenced** in these articles;
their problem gate and opportunity grade stay `PENDING`, with no numeric
opportunity score. They are separate products by the same founder, so they
were not merged. No new problem, signal or idea was created in this pass.

The CEVF event report now derives its event name from the report lead. Direct
event evidence takes precedence over an unrelated inherited follow-up ID.
BITO's sole-source event link was corrected from PizzaPitch to the CEVF report;
BITO itself and its source were not duplicated. Event navigation no longer
descends into arbitrary generic news/speaker links.

After all operations: **15 project rows / 7 visible**, 3 problems, 3 signals,
0 ideas, 1,109 unique candidates: 212 queued, 304 pending, 549 rejected,
19 event, 14 error, 7 published, 3 ecosystem and 1 problem. The 13 original
project UUIDs, original publication dates and `first_seen` timestamps were
retained unchanged. The queue is durable and archive coverage remains
incomplete. Two new project rows became visible; the forced/backfill/drain runs
alone added none. Repeated candidate processing can change current status
totals, so per-run decisions must not be added to current unique counts.

Read-only rechecks returned HTTP 200 for Hackathons.uz, IT Park Ventures and
Startup Uzbekistan. Hackathons.uz exposes event links, but a safe dated project
parser was not verified. All three remain disabled in the registry. Exa and
Vercel connectors were unavailable in this environment; no preview deployment
was attempted.

Verification: 189 Python tests, 12 Playwright desktop/mobile tests, Ruff,
TypeScript and Vite production build passed. The existing third-party
Starlette/httpx deprecation warning remains. A local service restart followed
by `verify_deployment.py --local --compare` preserved all seven visible project
IDs, publication dates and `first_seen` values. This verifies the current
workspace SQLite file across a service restart; it does not provide persistent
cloud storage. Stage 1 is not accepted; no Global work was started.
