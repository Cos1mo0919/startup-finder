# v3.1 Stage A — catalog foundation

- Branch: `feature/simple-catalog-pipeline`.
- Immutable baseline: `reports/pipeline-baseline.json` (15 projects; 2 published, 11 review, 2 rejected).
- Verified pre-migration SQLite backup: `/tmp/izlanish-v31-pre-migration.sqlite3`.
  Restore instructions: `reports/pipeline-restore.md`.
- Additive schema v7 stores catalog score, method, description, date estimate,
  provenance, excerpt, retry state and append-only classification/status/attribute
  histories. Historical IDs, first-seen/publication timestamps and source links
  matched the backup after migration.
- Versioned runtime prompt: `config/prompts/catalog_classifier_v1.txt`.
- Trusted source/page allowlist: `config/trusted_catalog_pages.json`. Its only
  initial entry is an explicit negative rule for IT Park news articles; Stage C
  must validate any positive trusted pair before adding it.
- `backend/app/catalog.py` validates enums, Uzbek description length, four
  1–10 factors, neutral fallback evidence flags and real-product claims. The
  computed score is the four-factor average. NOT_PROJECT below 0.7 goes to
  review. The keyless classifier returns `llm_unavailable` for generic pages.
- `backend/app/catalog_store.py` stores exact source excerpts, source links,
  histories and duplicate updates. LLM disagreement above 0.7 hides a formerly
  deterministic publication for admin review; lower confidence only flags it.
- Offline fixtures are hand-labeled excerpts of three saved real pages:
  KotibAI (PROJECT), Andijon university scholarship notice (NOT_PROJECT),
  CEVF project list (MULTI). Mock LLM responses validate the pipeline contract.
  This is **not** a measurement of real LLM classifier precision.

The older problem-first pipeline still handles production discovery at this
stage. Stage C will route project candidates through the v3.1 catalog flow.
