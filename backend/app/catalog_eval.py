"""Human-labeled saved-page benchmark; live provider runs are explicit only."""

import json
from collections import Counter
from datetime import datetime, timezone

from .config import ROOT
from .llm_service import LLMService, LLMUnavailable
from .raw_discovery import NOISE_TITLE, PROJECT_HINT
from .schemas import Article

BENCHMARK_PATH = ROOT / "tests/fixtures/catalog_eval.json"


def smoke(settings, factory=None):
    """One explicit live request; report validation and provider identity without source text or keys."""
    row = json.loads(BENCHMARK_PATH.read_text())[0]
    service = LLMService(settings, factory)
    if not service.available:
        return {"status": "llm_unavailable", "configured": False,
                "provider_order": [p.name for p in service.providers],
                "model": service.providers[0].model if service.providers else None}
    article = Article(url=row["url"], publisher="Saved source", title=row["title"], text=row["text"],
                      published_at=datetime(2026, 3, 10, tzinfo=timezone.utc), kind="news")
    try:
        analysis = service.analyze_source(article)
    except LLMUnavailable:
        return {"status": "failed", "configured": True,
                "provider_order": [p.name for p in service.providers],
                "provider_metrics": service.status()}
    return {"status": "completed", "configured": True,
            "classification": analysis.result.classification,
            "json_parseable": True, "schema_valid": True,
            "provider": analysis.provider, "model": analysis.model,
            "prompt_version": analysis.prompt_version,
            "attempt_count": analysis.attempt_count,
            "provider_metrics": service.status()}


def evaluate(settings, factory=None):
    rows = json.loads(BENCHMARK_PATH.read_text())
    service = LLMService(settings, factory)
    if not service.available:
        return {"status": "llm_unavailable", "cases": len(rows), "llm_quality_measured": False}
    results = []
    for row in rows:
        if NOISE_TITLE.search(row["title"]) and not PROJECT_HINT.search(row["title"]):
            results.append({"expected": row["expected_label"], "actual": "NOT_PROJECT",
                            "provider": "deterministic_prefilter", "model": None})
            continue
        article = Article(url=row["url"], publisher="Saved source", title=row["title"], text=row["text"],
                          published_at=datetime(2026, 3, 10, tzinfo=timezone.utc), kind="news")
        try:
            analysis = service.analyze_source(article)
            results.append({"expected": row["expected_label"], "actual": analysis.result.classification,
                            "provider": analysis.provider, "model": analysis.model})
        except LLMUnavailable:
            results.append({"expected": row["expected_label"], "actual": None})
    positives = {"PROJECT", "MULTI"}
    tp = sum(r["expected"] in positives and r["actual"] in positives for r in results)
    fp = sum(r["expected"] not in positives and r["actual"] in positives for r in results)
    fn = sum(r["expected"] in positives and r["actual"] not in positives for r in results)
    labels = {"expected": dict(Counter(r["expected"] for r in results)),
              "actual": dict(Counter(r["actual"] or "FAILED" for r in results))}
    return {"status": "completed" if all(r["actual"] for r in results) else "partial",
            "cases": len(rows), "llm_quality_measured": all(r["actual"] for r in results),
            "labels": labels, "provider_metrics": service.status(),
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "false_positives": fp, "false_negatives": fn, "results": results}
