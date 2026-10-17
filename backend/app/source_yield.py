"""Recent daily-worker yield, advisory ordering only; never disables sources."""
from collections import Counter
from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import select
from .db import RegistrySource, Run, now_utc

MIN_CANDIDATES = 10


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
            if item.get("reason") in {"llm_unavailable", "llm_retry_exhausted"}:
                row["counts"]["llm_unavailable"] += 1
    return [{**row, "counts": {key: row["counts"][key] for key in
             ("candidates", "published", "rejected", "review_required", "llm_unavailable", "fetch_failed")},
             "deprioritized": row["counts"]["candidates"] >= MIN_CANDIDATES and row["counts"]["published"] == 0,
             "minimum_candidates": MIN_CANDIDATES, "window": "last_20_runs_7_days"}
            for row in sorted(counts.values(), key=lambda row: (-row["counts"]["candidates"], row["name"]))]
