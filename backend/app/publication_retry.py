"""Bounded publication retries; validated LLM results survive rollback."""
from datetime import timedelta

from sqlalchemy import or_, select

from .catalog_store import history
from .db import Candidate, RawDiscovery, now_utc
from .raw_discovery import record_transition

MAX_FAILURES = 3


def eligible(now=None):
    retry = Candidate.article["_publication_retry"]
    failures = retry["failures"].as_integer()
    due = retry["next_attempt_at"].as_string()
    return (or_(failures.is_(None), failures < MAX_FAILURES),
            or_(due.is_(None), due <= (now or now_utc()).isoformat()))


def record_failure(factory, url, exc, run_id=None):
    """Separate transaction after publication rollback, without error parameters."""
    with factory.begin() as session:
        row = session.get(Candidate, url)
        if row is None or not (row.article or {}).get("_validated_catalog_result"):
            return
        now = now_utc()
        failures = int(row.article.get("_publication_retry", {}).get("failures", 0)) + 1
        exhausted = failures >= MAX_FAILURES
        reason = "publication_retry_exhausted" if exhausted else "publication_retry_scheduled"
        row.article = {**row.article, "_publication_retry": {
            "failures": failures, "max_failures": MAX_FAILURES,
            "next_attempt_at": None if exhausted else (now + timedelta(minutes=5 * 2 ** (failures - 1))).isoformat(),
            "last_error_class": type(exc).__name__,
        }}
        row.status = "review_required" if exhausted else "queued"
        row.reason, row.updated_at = reason, now
        row.attempts += 1
        row.last_run_id = run_id
        row.processing_version = 8
        row.status_history = history(row.status_history, row.status, "publication_retry", reason, now)
        raw = session.scalar(select(RawDiscovery).where(RawDiscovery.source_url == url))
        if raw is not None:
            record_transition(raw, "review_required" if exhausted else "pending", reason, when=now)
