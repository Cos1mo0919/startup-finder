"""Public catalog ranking; neutral fallback is never exposed as a score."""

from .db import aware, now_utc


def rank(project, at=None, neutral=4.5):
    at = at or now_utc()
    base = project.catalog_score if project.catalog_score is not None else neutral
    age = max(0, (at - aware(project.published_at)).days)
    recency = max(0.0, 1.0 - age / 365)
    reality = min(0.6, (project.catalog_scores or {}).get("real_product", 0) * 0.06)
    evidence = min(0.4, (project.evidence_count or 0) * 0.1)
    sparse = 0.2 if (project.evidence_count or 0) < 3 else 0.0
    return round(base + recency + reality + evidence - sparse, 3)
