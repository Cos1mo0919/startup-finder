"""Human-labeled saved-page benchmark; live provider runs are explicit only."""

import json
from datetime import datetime, timezone

from .config import ROOT
from .llm_service import LLMService, LLMUnavailable
from .schemas import Article

BENCHMARK_PATH = ROOT / "tests/fixtures/catalog_eval.json"


def evaluate(settings, factory=None):
    rows = json.loads(BENCHMARK_PATH.read_text())
    service = LLMService(settings, factory)
    if not service.available:
        return {"status": "llm_unavailable", "cases": len(rows), "llm_quality_measured": False}
    results = []
    for row in rows:
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
    return {"status": "completed" if all(r["actual"] for r in results) else "partial",
            "cases": len(rows), "llm_quality_measured": all(r["actual"] for r in results),
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "false_positives": fp, "false_negatives": fn, "results": results}
