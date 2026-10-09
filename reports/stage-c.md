# v3.1 Stage C — discovery operations and live check

## Implementation

The hourly and morning/evening reconciliation project scans now call
`CatalogPipeline`; existing weekly Uzbekistan and monthly Global deep problem
scans still use the older intelligence pipeline. Yearly CLI backfill passes its
window to the catalog discovery adapter. The original SQLite records remain
intact. Discovery links enter a durable candidate queue. The new processor
runs the cheap noise check first, then LLM classification if configured;
otherwise a generic article waits with `llm_unavailable`. Only a deliberately
approved structured adapter/page type can publish without AI. The allowlist
at `config/trusted_catalog_pages.json` has no positive production entry yet.

Candidate and project classification/status histories, raw source excerpts,
analysis and publication methods, source identity, HN discovery URL when the
feed provides one, estimated dates and source yield are retained. Owner APIs
and `/admin/catalog` support Publish, Hide, Reject and Merge; Merge transfers
source/evidence links, keeps the duplicate record and preserves earliest
`first_seen`. Recent filters exclude estimated dates.

## Keyless live runs (local SQLite, 2026-10-09)

| Source | Checked | Fetched URLs | New candidate rows | Processed | Published | Review | Rejected | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Spot startup section | 1 | 21 source links | 0 | 3 | 0 | 3 | 0 | 0 |
| Show HN public RSS mirror | 1 | 20 | 20 | 30 | 0 | 26 | 0 | 4 |

Spot run 67 accidentally also followed 8 existing event links before the
`--only-source` restriction was corrected. No new candidate rows resulted.
Show HN run 68 was `partial` because four maker URLs returned
`article_body_missing`: vendiq.rishailabs.com, signalhub.trade,
tryveil.app/architecture and hangul.ink/blog/hangul-day. These errors are
isolated; the other candidates were processed. The 30-item processing budget
included ten already queued URLs, so processed is larger than newly fetched.

No `AI_API_KEY` or `SEARCH_API_KEY` was configured. No LLM run or real LLM
precision measurement was possible. The hand-labelled offline fixture covers
PROJECT, NOT_PROJECT and MULTI with mocked model responses; it validates the
contract, not live precision. A trusted deterministic auto-publication was
verified with an isolated test adapter. No active production source/page pair
was positively allowlisted, so live automatic-publication precision and volume
are both unmeasured (0 live publications), not 100%.

### Audit examples

- AUTO_PUBLISHED: no new live v3.1 auto-publication. The isolated trusted-page
  test publishes `AgroKo‘mak` from a fixture with score `null`, evidence count
  zero and original text. This is a test artifact and not a database project.
- REVIEW_REQUIRED: `https://leafovers.com/` remains in admin review with
  `llm_unavailable`; a Show HN mention and project site alone are insufficient
  for keyless auto-publication from this untrusted generic page.
- REJECTED: `https://www.spot.uz/oz/2026/02/23/venture-company` is a retained
  older rejection (`not_project`), concerning a venture financing company
  announcement rather than a particular product. The v3.1 live runs rejected
  zero candidates.

## Preservation and counts

The immutable pre-migration baseline is `reports/pipeline-baseline.json`:
15 projects (2 published, 11 review, 2 rejected) and 1,136 candidate records.
After these two bounded runs: still 15 projects (2/11/2), 1,156 candidates,
including 33 in v3.1 review, 262 old pending, 206 queued and 18 errors.
Neither DMED nor KotibAI was recreated or modified by these two runs. The
2 published records still use the legacy method; deterministic v3.1 published
0, LLM published 0, hybrid/enriched 0. The legacy records have no catalog
score, so `score_pending` is true there. No new Uzbekistan or Global project
was published. Remaining queue and missing keys limit yield; they are not
quality evidence against all source material.

## Risks and next measured step

Most generic articles remain review-required without an LLM key. The active
project-first candidates still need a validated structured official adapter
before keyless automatic publication can have real throughput. Some maker
sites omit extractable text. The older 262 pending and 206 queued records have
not all been reprocessed under the bounded 30-per-run budget; successive
`--drain` runs continue them without deleting history. Classification of
non-English text, high confidence NOT_PROJECT decisions, and live score
calibration still require a configured LLM and a labelled review sample.

Checks: 233 backend tests, 10 desktop/mobile browser tests, Ruff, TypeScript
and Vite production build. The only test warning is the existing
Starlette/httpx deprecation notice. Pre-migration backup/restore:
`reports/pipeline-restore.md`.
