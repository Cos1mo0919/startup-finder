"""Recent daily-worker yield, advisory ordering only; never disables sources."""
from collections import Counter
from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import select
from .db import RegistrySource, Run, now_utc

MIN_CANDIDATES = 10
# Outcomes caused by our own limits (LLM down/quota, run budget, slow database)
# say nothing about the source, so they never count toward deprioritization.
UNEVALUATED_REASONS = {"llm_unavailable", "llm_retry_exhausted"}
UNEVALUATED_STAGES = {"budget_stopped", "timeout", "worker_failed", "no_decision"}


def evaluated(item):
    return item.get("reason") not in UNEVALUATED_REASONS and item.get("stage") not in UNEVALUATED_STAGES


def recent_yield(session, current=None):
    sources = list(session.scalars(select(RegistrySource)))
    by_name = {s.name: s.id for s in sources}
    by_domain = {urlsplit(s.url).hostname: s.id for s in sources}
    names = {s.id: s.name for s in sources}
    reports = list(session.scalars(select(Run.details).where(
        Run.started_at >= now_utc() - timedelta(days=7),
        Run.details["mode"].as_string() == "free_daily",
    ).order_by(Run.id.desc()).limit(20)))
    if current:
        reports = [report for report in reports if report.get("candidate_runs") != current]
        reports.append({"candidate_runs": current})
    counts = {}
    for report in reports:
        for item in report.get("candidate_runs", []):
            source = item.get("source", {})
            identifier = source.get("id") or by_name.get(source.get("name")) or by_domain.get(source.get("domain"))
            key = identifier or source.get("domain") or "unknown"
            row = counts.setdefault(key, {"source_id": identifier, "name": names.get(identifier, source.get("name", key)),
                                         "domain": source.get("domain", ""), "counts": Counter()})
            row["counts"]["candidates"] += 1
            row["counts"][item.get("stage", "unknown")] += 1
            if item.get("reason") in UNEVALUATED_REASONS:
                row["counts"]["llm_unavailable"] += 1
            if evaluated(item):
                row["counts"]["evaluated"] += 1
    return [{**row, "counts": {key: row["counts"][key] for key in
             ("candidates", "evaluated", "published", "rejected", "review_required", "llm_unavailable", "fetch_failed")},
             "deprioritized": row["counts"]["evaluated"] >= MIN_CANDIDATES and row["counts"]["published"] == 0,
             "minimum_candidates": MIN_CANDIDATES, "minimum_basis": "evaluated", "window": "last_20_runs_7_days"}
            for row in sorted(counts.values(), key=lambda row: (-row["counts"]["candidates"], row["name"]))]
