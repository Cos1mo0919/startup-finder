# Publication consistency audit — local cloud SQLite, 2026-10-10

This audit concerns the SQLite file in this checkout. The user's Codespace has
a different database (reported: 10 published candidates and 2 public projects),
which was not available here. These counts must not be presented as its results.

The user provided a Codespace candidate listing. Its ten published URLs are
All Things Banana, Piet in Piet, Woodpecker, Uzbekistan Airways, Agroko‘makchi,
DMED, Tumar Innovation Hub, KotibAI, the CEVF article linked to BITO, and
Turan Security. Six have current `entity_type=IGNORE`, four have `PROJECT`.
The listing contains `project.visible=true` but does not contain
`Project.publication_status`, classifier confidence or full source excerpts.
Thus it establishes a stale legacy-type problem but cannot by itself explain
which eight canonical projects the public API excludes. The updated
`--inspect-url` now exposes the missing fields in that environment after pull.

The old problem migration could call `refresh_publication()` on catalog rows
with an old Analysis-shaped content object, withdrawing a real catalog card
because optional problem analysis was pending. It now leaves catalog publication
unchanged. Reconciliation restores an old-gate withdrawal only with an exact
source link, the original published candidate, and either validated LLM
PROJECT confidence ≥0.7 or historical creator/fact evidence. The exact
Codespace statuses still require inspection in that database.

Before repair: 12 published candidate URLs, 11 canonical `PUBLISHED` projects;
10 published candidates had the stale legacy `entity_type=IGNORE`. After an
exact source/project reconciliation: 12 published candidate URLs, all currently
`PROJECT`; 11 canonical public projects; `/api/projects` and
`/api/catalog/home` both return 11. A multi-project source explains why candidate
and project counts need not be equal. The database was backed up before repair
to `/tmp/izlanish-before-publication-repair.sqlite3`.

| Source subject | Stored classifier result / confidence | Source evidence and assessment | Local final public status |
| --- | --- | --- | --- |
| All Things Banana | `NEEDS_EXTRACTION` / 0.5 (keyless fallback) | Its homepage is a portal for banana news, recipes, puzzles and games; it does not describe one canonical startup or product. | Review, hidden; no project row. |
| Piet in Piet | `NEEDS_EXTRACTION` / 0.5 (keyless fallback) | The page describes a working self-referential Piet/Blimp program; this can qualify as a concrete software prototype under the current catalog rule. | Review, hidden locally; no project row or verified LLM result here. |
| Tumar Innovation Hub | `NEEDS_EXTRACTION` / 0.5 (keyless fallback) | The Spot article announces a webinar on entry to the UAE market, not a Tumar product launch. | Review, hidden; no project row. |
| Turan Security | No exact candidate/source record in this SQLite file | The live Spot article was fetched without bypassing restrictions. It describes cybersecurity services and a Threat Intelligence product, beyond the competition headline. | No local project row; Codespace canonical status unverified. |
| Woodpecker | `NON_PROJECT` / confidence not stored (older detector) | A Show HN post has a first-person creator statement, official link to `oakery.io` and browser-agent demo. This appears to describe a concrete project, but the old rejection has not been replaced by a validated catalog classification. | Rejected under old classification, hidden; warrants reprocessing/review. |

An attempted read-only Gemini recheck of four locally stored pages timed out.
No new LLM classification or confidence is claimed. The old classifier labels
above are taken only from the stored candidate rows, not inferred from the
source text. The Codespace's five claimed newly processed outcomes cannot be
verified without that database or a diagnostic export.

Based on the source evidence, the intended Codespace disposition is:
**All Things Banana** and **Tumar Innovation Hub** stay hidden under the
exact-URL manual review list; **Piet in Piet**, **Woodpecker** and
**Turan Security** are eligible to remain published if their saved LLM
classifications meet the existing confidence and source requirements. The
Codespace LLM confidences were not supplied and are not inferred here.
