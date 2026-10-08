# Problem-first implementation plan

The existing SQLAlchemy/SQLite models, durable candidate queue, evidence gates,
source registry, archive traversal, Uzbek date formatter and hourly collector remain
the base. No production rows are reset or seeded as sample products.

1. Additive schema migration: structured problem gate on projects; problems,
   problem evidence, project links, solution hypotheses, richer signals and durable
   scheduler checkpoints. Existing IDs, URLs, publication dates and first_seen stay.
2. Conservative classification and problem analysis before opportunity promotion.
   Unknown pain, customer, frequency, cost or market data stay unknown. Only
   source-backed statements become problem records; existing cards lacking support
   become pending problem analysis, not fabricated opportunities.
3. Add explanatory opportunity rubric and stop states beside the existing
   Foydalilik/Tasdiqlanganlik scores. No A/B grade from unknown inputs.
4. Extend the seed registry with verified/current sources and disabled source
   concepts. Preserve operator switches and health on ordinary startup.
5. Keep hourly discovery; add morning/evening reconciliation, weekly Uzbekistan
   local and monthly cross-country problem scans with persisted checkpoints.
6. Add read-only Uzbek dashboard/pages for problems, solution hypotheses,
   signals, sectors and source health. Keep project archive/search and links.
7. Run migration, tests, lint, build, browser/server checks and an isolated
   keyless discovery sample. Document actual coverage and limits.

The old standalone Global stage is not started. Monthly cross-country problem
signals are a scope within this product and never become Uzbekistan projects.
