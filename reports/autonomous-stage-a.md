# Autonomous discovery engine — Stage A

Baseline commit: `866e097`. The pre-migration baseline is
`reports/pipeline-baseline.json`; the v3.1 baseline was preserved separately
as `reports/pipeline-baseline-v3.1.json`.

A consistent pre-migration SQLite backup is documented in
`reports/autonomous-pipeline-restore.md`. Schema v8 adds `raw_discoveries`
and `llm_provider_health` without changing project rows. A live schema check
confirmed all 15 project IDs, first-seen/publication dates and existing
project-source links match the backup exactly.

Raw observations are idempotent by `(source_adapter, source_url)` and by
`(source_adapter, external_id)` when supplied. They retain payload, dates,
processing states/reasons and append-only transition history. Cheap checks
only reject obvious title noise and skip an already-attached source URL;
ambiguous items continue to classification.

`LLMService` provides Gemini, OpenRouter, Groq and OpenAI adapters behind one
validated catalog result contract. It records provider metrics and uses bounded
retries, ordered fallback and a per-window circuit breaker. It is not yet
wired into production processing; that is Stage B. The existing classifier
remains active until then.

Verification before Stage B: 238 backend tests passed, including new raw
idempotency, filtering, provider fallback/circuit and schema preservation
checks. Ruff passed. One existing Starlette/httpx deprecation warning remains.
