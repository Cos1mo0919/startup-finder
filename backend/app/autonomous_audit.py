"""Non-mutating audit for the autonomous catalog rollout."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select

from .config import ROOT
from .db import Candidate, Project, ProjectDeepAnalysis, ProviderHealth, RawDiscovery, Run, aware


def audit(factory, baseline_path=ROOT / "reports/pipeline-baseline.json"):
    baseline = json.loads(baseline_path.read_text())
    captured = datetime.fromisoformat(baseline["captured_at"])
    with factory() as session:
        projects = session.scalars(select(Project)).all()
        raws = session.scalars(select(RawDiscovery)).all()
        candidates = session.scalars(select(Candidate)).all()
        runs = session.scalars(select(Run).order_by(Run.id.desc()).limit(10)).all()
        providers = session.scalars(select(ProviderHealth)).all()
        deep = session.scalars(select(ProjectDeepAnalysis)).all()
        source_yield = defaultdict(Counter)
        for raw in raws:
            bucket = source_yield[raw.source_adapter]
            bucket["raw_discoveries"] += 1
            bucket[raw.status] += 1
            if raw.canonical_project_id:
                bucket["project_links"] += 1
        for run in runs:
            if not (run.details or {}).get("mode", "").startswith("catalog_"):
                continue
            for source, metrics in (run.details or {}).get("source_yield", {}).items():
                for metric, amount in metrics.items():
                    source_yield[source][f"run_{metric}"] += amount
        fresh = [p for p in projects if aware(p.first_seen) >= captured and p.publication_status == "PUBLISHED"]
        randomizer = random.Random(20261010)
        review = [r for r in raws if r.status == "review_required"]
        rejected = [r for r in raws if r.status == "rejected"]
        randomizer.shuffle(review)
        randomizer.shuffle(rejected)
        return {
            "baseline": baseline,
            "final": {"total_projects": len(projects),
                      "published": sum(p.publication_status == "PUBLISHED" for p in projects),
                      "review_required": sum(p.publication_status == "REVIEW_REQUIRED" for p in projects),
                      "rejected": sum(p.publication_status == "REJECTED" for p in projects),
                      "raw_discoveries": len(raws),
                      "raw_status": dict(Counter(r.status for r in raws)),
                      "candidate_status": dict(Counter(c.status for c in candidates)),
                      "deep_analysis": dict(Counter(d.status for d in deep))},
            "provider_metrics": [{"name": p.name, "requests": p.requests, "successes": p.successes,
                                  "fallbacks": p.fallback_count, "last_error": p.last_error} for p in providers],
            "source_yield": {key: dict(value) for key, value in sorted(source_yield.items())},
            "new_projects": [{"id": p.id, "name": p.name, "country": p.country,
                              "published_at": p.published_at.isoformat(), "source_urls": [s.url for s in p.sources],
                              "catalog_score": p.catalog_score, "analysis_method": p.analysis_method,
                              "publication_reason": p.publication_reason}
                             for p in fresh],
            "samples": {
                "auto_published": [{"name": p.name, "country": p.country,
                                    "source": p.sources[0].url if p.sources else None,
                                    "reason": p.publication_reason,
                                    "evidence": (p.publication_excerpt or "")[:250]} for p in fresh[:25]],
                "review_required": [{"source": r.source_url, "reason": r.failure_reason,
                                     "evidence": (r.raw_text or r.description or r.title)[:250]}
                                    for r in review[:10]],
                "rejected": [{"source": r.source_url, "reason": r.failure_reason,
                              "evidence": (r.raw_text or r.description or r.title)[:250]}
                             for r in rejected[:10]],
            },
        }
