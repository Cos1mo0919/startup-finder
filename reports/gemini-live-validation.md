# Gemini live catalog validation — 2026-10-10

## Configuration and checks

- `GEMINI_API_KEY`: configured in this cloud process; its value was never printed.
- Provider order: Gemini, OpenRouter, Groq, OpenAI. Only Gemini had a key.
- Model: `gemini-3.1-flash-lite`; prompt `catalog_classifier_v2`.
- Live smoke: PROJECT, parseable JSON, valid business schema, provider/model metadata recorded.
- Human-labeled live pipeline benchmark: 3 cases (PROJECT 1, MULTI 1, NOT_PROJECT 1), all 3 correct; precision 1.0, recall 1.0, 0 false positives and 0 false negatives. One NOT_PROJECT was caught by the normal cheap scholarship prefilter; two cases called Gemini. The benchmark is far too small to establish general accuracy. Earlier raw-LLM-only attempts misclassified the scholarship and failed MULTI validation; keep auditing new publications.
- The old default `gemini-2.5-flash` returned HTTP 404 for this new key. `gemini-3.8-flash` did not answer within 60–120 seconds in this environment. Neither result was treated as a valid classification.

## Backlog and publication

Before: 15 project records, 2 published; 598 raw discoveries, of which 473 were in review, 71 rejected, 21 processed, 10 pending and 23 failed. Candidate queue: 111 queued.

After bounded processing and audit: 28 project records, 11 published, 14 review, 2 rejected, 1 duplicate. Raw discoveries: 455 review, 79 rejected, 31 processed, 10 pending, 23 failed. Candidate queue: 111 queued. The raw table was preserved. Run IDs 80–87 processed 61 candidate attempts, including one address recheck and a fresh Show HN queue drain. Provider health at report time: 69 Gemini requests, 30 validated successes and 25 fallbacks across smoke tests, benchmarks and catalog runs; 2 timeouts and 30 schema/business validation failures. No other provider was configured. These are cumulative provider counts, not just backlog counts.

Nine new cards remain published after manual audit:

| Source family | Project | Country on card | Original URL |
| --- | --- | --- | --- |
| UzHunt | Top3 | Uzbekistan | https://uzhunt.uz/p/top-3 |
| UzHunt | Postpublish Pro | Uzbekistan | https://uzhunt.uz/p/postpublish-pro |
| UzHunt | Screenspell | Unknown | https://uzhunt.uz/p/screenspell |
| UzHunt | Repost21 | Uzbekistan | https://uzhunt.uz/p/repost21 |
| UzHunt | Sovereign | Unknown | https://uzhunt.uz/p/sovereign |
| Show HN | Screens | United States | https://chromewebstore.google.com/detail/screens-beautiful-screens/fcnblpibmdpipbdfomiicdaadjmidakc |
| Show HN | Clanking | Unknown | https://github.com/chrchr/clanking |
| Show HN | aimAndShoot | Unknown | https://github.com/victorqribeiro/aimAndShoot |
| Show HN | tgv | Unknown | https://github.com/zeqianli/tgv |

Top3 and Postpublish Pro have estimated first-source dates, clearly marked as such in the UI. Unknown countries were not inferred from the discovery feed. The Global country tab currently shows Screens; the other international-feed items remain in All until their country is verified.

The Next Rise IT Park article initially produced four cards from a MULTI response. Unitlab, Smartup and OsonSoft were hidden to review because the article does not substantiate the LLM's concrete product descriptions. Its second DMED card was merged into the original 2025 DMED ID with the new IT Park source retained. A same-name/conflicting-creator match now routes to duplicate review instead of creating a second card. These corrections preserve all rows and provenance.

## Source yield in recent runs

The read-only audit aggregates the most recent catalog runs, so MULTI results can make outcome counts exceed processed source-page counts.

| Source | Raw records | Processed attempts | Auto-publish decisions | Review decisions | Reject decisions | Current result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| UzHunt | 7 | 12 | 5 | 7 | 0 | 5 public cards |
| Show HN | 49 | 43 | 4 | 39 | 0 | 4 public cards |
| IT Park | 26 | 9 | 4 | 2 | 6 | 3 hidden, 1 merged; no net new public card |
| Spot Startups | 21 | 2 | 0 | 1 | 1 | no new public card |
| ICT Week | 4 | 1 | 0 | 0 | 1 | no new public card |

A fresh Spot Startups fetch checked 20 known links and found no new candidate. A fresh Show HN fetch returned HTTP 502, while ten previously stored queue items still ran. This is a partial source result, not a successful fresh fetch. One failing source did not block queue processing.

## Public and operational validation

Against the actual database, `/api/health`, `/api/projects`, Uzbekistan and Global catalog queries, `/api/catalog/home`, project detail and authenticated `/api/admin/status` returned HTTP 200. Public totals were consistent at 11; Uzbekistan country tab had 5 and Global country tab had 1. All 11 public cards had a description. Two legacy cards remain honestly unscored. Hidden Next Rise cards did not appear publicly. Publication dates and historical IDs were preserved.

No deterministic-published card currently awaits hybrid reanalysis. Telegram ingestion and alert credentials are absent; this did not block Gemini work. Deep Excel weights remain unvalidated, so deep weighted analysis remains optional and unpublished projects are not promoted by score.

The detailed audit is in `reports/gemini-live-audit.json`: 9 public-project samples, 10 random review samples and 10 random rejected samples, each with source, classification, confidence, reason and a brief assessment.

The consistent pre-run backup is `/tmp/izlanish-before-gemini-2026-10-10.sqlite3`. To restore it after stopping the API and scheduler (this discards all subsequent discoveries), run from the repository root:

```bash
.venv/bin/python -c 'import sqlite3; source=sqlite3.connect("/tmp/izlanish-before-gemini-2026-10-10.sqlite3"); target=sqlite3.connect("data/finder.sqlite3"); source.backup(target); target.close(); source.close()'
```

The remaining backlog is large and Gemini occasionally fails business validation. The scheduler will retry eligible records with bounded batches and six-hour backoff; the three-case benchmark cannot justify claiming high real-world precision. This report records the current observed state, not completion of the entire archive or user acceptance.
