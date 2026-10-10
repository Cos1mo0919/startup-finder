# Autonomous discovery rollout: keyless validation (2026-10-10)

The immutable baseline was 15 projects: 2 published, 11 in review, 2 rejected;
`raw_discoveries` did not exist. The final local database still has the same 15
projects and 2 public cards. No fabricated card was added. The pre-migration
backup and exact restore command are in `autonomous-pipeline-restore.md`.
The final SQLite integrity check returned `ok`; comparison with that backup
found zero missing/changed `(project ID, first_seen, published_at)` rows and
zero missing/changed `(source ID, project ID, URL)` rows.

## Live run and backlog

The first forced keyless run checked 12 enabled sources, stored 177 discovered
URLs before classification, processed 30, put 29 into owner review and recorded
one robots.txt denial. Subsequent bounded queue drains and 201 cached legacy
review rechecks and a fresh-window recovery pass produced a final inventory
of 598 raw observations (including legacy candidate imports): 473 review,
71 rejected, 21 processed, 23 failed and 10 pending. The candidate queue still
has 111 queued entries. Reasons and
source excerpts remain attached to individual records. `--inspect-raw ID`
returns the trace. Two unrelated Nobel articles were reclassified from review
to `obvious_noise` rejection after an intentionally narrow rule change.
The fresh pass recovered 19 October items that had been rejected solely
because a prior archive run used a January–September window. Their source text
and dates were preserved; without an LLM they moved to `llm_unavailable`
review instead of being silently lost.

The source-yield details and random audit samples are in `autonomous-audit.json`.
The initial fetch yielded 21 Spot Startups, 7 UzHunt, 13 IT Park, 3 ICT Week,
19 Show HN, 20 each Spot Uzbek/Russian, 20 Gazeta and regional university
links. Project-first source types now receive queue priority over generic news.
Across all old and new raw rows, BuxDU had 9 page errors, IT Park 6, Show HN 7
and NamDU 1; these are isolated page/parser or robots failures, not proof that
the entire source was unavailable. No automatic source block or robots bypass
occurred.

## Publication and audit

New Uzbekistan cards: **0**. New Global cards: **0**. Newly published card
sample size: **0**, so publication precision cannot be estimated from this
run. Random owner-review samples contain some plausible projects and some
general news; all remain unpublished because no LLM provider was configured
and no positive deterministic trust pair was approved. Random rejected samples
mostly show unrelated updates, explicitly excluded dates and clear noise.
This is a limited keyless result, not evidence of the requested higher live
project yield. Broader yield requires provider-backed classification or an
operator-approved structured `(adapter, page_type)` after page-level review.
Neither evidence standards nor publication thresholds were reduced.

LLM provider order is Gemini → OpenRouter → Groq → OpenAI. Configured provider
count, requests, successful responses and fallbacks were all **0** in this
environment. The saved-page benchmark has three hand-labeled sources; live
evaluation reports `llm_quality_measured=false`. No honest live precision or
recall number is available. Deterministic new publication count: **0**.

Telegram ingestion is implemented through Telethon and the same raw queue, but
no channels or credentials are configured; live ingestion count is **0**.
The separate admin alert bot has no token/chat configured and sent **0**
messages. Deep analysis is scheduled after publication; no provider was
available and no newly analyzed project exists. Historical Excel weights were
not validated, so final weighted score remains null. `config/deep_score_weights.json`
records this state. `config/trusted_catalog_pages.json` remains the publication
allowlist and has no positive production entry.

Final local checks: 260 backend tests passed; Ruff passed; TypeScript/Vite
production build passed; 10 desktop/mobile Playwright checks passed. The
three hand-labeled saved-page cases also run within the backend suite. This
report does not certify live provider or Telegram behavior.
