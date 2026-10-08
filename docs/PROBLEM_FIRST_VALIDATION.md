# Problem-first keyless validation — 08.10.2026

This report separates a clean, bounded discovery run from reprocessing two URLs
that the run itself found. It describes the local SQLite copy only; the database
file is intentionally not committed. No AI or paid search keys were present.

## Reproduce

```bash
DATABASE_URL=sqlite:////tmp/izlanish-clean-priority.sqlite3 \
AI_API_KEY= OPENAI_API_KEY= SEARCH_API_KEY= TRUSTED_EGRESS_PROXY=true \
MAX_CANDIDATES=30 ARCHIVE_PAGES=12 FETCH_TIMEOUT=8 \
.venv/bin/python -m backend.app.cli --backfill \
  --from-date 2022-01-01 --to-date 2026-09-30 \
  --report /tmp/izlanish-clean-priority.json
```

The database did not exist before the command. Each year checked 12 enabled
sources; 64 entries were registered. Four enabled sources were university
sources. `MAX_CANDIDATES=30` currently permits up to 60 processing attempts per
year. The archive page budget was 12. This is bounded coverage, not a claim to
have exhausted every archive. The 789 unique discovered URLs remained durable
in the queue or had an explicit processing status.

| Year | Source checks | URLs found | Processed | New projects | Rejected | Pending | Signals | Problems |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | 12 | 318 | 60 | 1 | 30 | 26 | 2 | 1 |
| 2023 | 12 | 324 | 60 | 0 | 34 | 24 | 2 | 0 |
| 2024 | 12 | 355 | 60 | 0 | 38 | 22 | 0 | 0 |
| 2025 | 12 | 361 | 60 | 1 | 35 | 23 | 0 | 0 |
| 2026 Jan–Sep | 12 | 391 | 60 | 1 | 29 | 24 | 2 | 0 |

All five year runs reported `partial`. There were 166 rejection decisions:
153 `not_project`, 11 `noise_topic`, and 2 `unknown_publication_date`.
One additional `blocked_source` reason accompanied an error candidate rather
than a rejected candidate. The exact per-run counts are in the JSON report.
Three HTTP 503 errors occurred: Show HN RSS in 2022
and 2024, and one ICT Week article parser fetch in 2026. Other sources kept
running. No duplicate project was created. No project came from a university
source in this bounded sample.

The automated backfill published Uzbekistan Airways (2022), DMED (2025), and
KotibAI (2026). It discovered the Agroko‘makchi and CEVF URLs, but did not
finish both within their year budgets. The following address-specific queue
processing used those discovered URLs with the same evidence gates:

```bash
DATABASE_URL=sqlite:////tmp/izlanish-clean-priority.sqlite3 \
AI_API_KEY= OPENAI_API_KEY= SEARCH_API_KEY= TRUSTED_EGRESS_PROXY=true \
.venv/bin/python -m backend.app.cli --reclassify-url \
  'https://www.spot.uz/oz/2023/11/22/agrokomakchi'

DATABASE_URL=sqlite:////tmp/izlanish-clean-priority.sqlite3 \
AI_API_KEY= OPENAI_API_KEY= SEARCH_API_KEY= TRUSTED_EGRESS_PROXY=true \
.venv/bin/python -m backend.app.cli --reclassify-url \
  'https://www.spot.uz/oz/2026/04/06/cevf'
```

The first added one project. The second initially remained pending because the
forum report title did not contain a literal event-type word. A narrow event
report recognition fix made the second retry identify the event and publish
BITO, with one event-project link. This change did not change publication
thresholds or invent a founder.

| Project | Date | Creator / organization | Problem gate | Legacy Foydalilik / Tasdiqlanganlik | Original source |
| --- | --- | --- | --- | --- | --- |
| Uzbekistan Airways | 19.07.2022 | Uzbekistan Airways | PENDING | 3.85 / 7.02 | https://www.spot.uz/oz/2022/07/19/uzbekistan-airways-app |
| Agroko‘makchi | 22.11.2023 | Qishloq xo‘jaligi vazirligi | PENDING | 2.85 / 7.02 | https://www.spot.uz/oz/2023/11/22/agrokomakchi |
| DMED | 07.01.2025 | Uzinfocom | PASS: prescription error risk | 2.10 / 6.72 | https://www.spot.uz/oz/2025/01/07/dmed |
| KotibAI | 10.03.2026 | Hikmatilla Ubaydullaev | PASS: transcription time | 4.85 / 6.72 | https://www.spot.uz/oz/2026/03/10/kotibai |
| BITO | 06.04.2026 | Umidjon Po‘latov | PENDING | 1.85 / 6.72 | https://www.spot.uz/oz/2026/04/06/cevf |

All five original source links were present as project-source citations.
Agroko‘makchi and BITO are real products with attributable source passages,
but their article passages do not independently establish a sufficiently
concrete problem. They are published as projects, not graded strong
opportunities. DMED and KotibAI have source-backed problem links, but still
lack cited data for all 15 opportunity criteria. No A/B grade or solution idea
was fabricated.

Final unique database state after the two targeted operations: 5 visible
projects, 3 problems, 6 signals, 0 solution ideas, 118 pending candidates,
166 rejected, 488 queued, 4 event candidates, and 1 error candidate. The
single 2022 problem not tied to a project is the sourced HUMO card outage.
2024 had no verified project in this bounded sample; its remaining archive
queue must be processed before drawing a coverage conclusion.

The existing Cloud database was separately backed up before reanalysis. All
12 pre-existing project UUIDs, dates and `first_seen` timestamps survived.
It ended with 13 project rows, 5 visible cards, 3 problems, 3 signals and no
ideas. This is not the same database as the clean run above.

Validation: 185 Python tests, 12 Playwright desktop/mobile tests, Ruff,
TypeScript/Vite build, API route smoke, actual-data browser checks and one
backend restart passed. The existing Starlette/httpx deprecation warning
remains. Mobile and desktop screenshots were inspected; no horizontal
overflow or JavaScript error was observed. Scheduler jobs were tested, but
an uninterrupted hourly production service was not operated during this run.
