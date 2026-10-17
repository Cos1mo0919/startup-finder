"""Recoverable LLM-unavailable reviews, with bounded automatic retries."""
from datetime import timedelta
from sqlalchemy import or_
from .db import Candidate, now_utc

MAX_FAILURES = 3


def eligible(now=None):
    retries = Candidate.article["_llm_retry"]
    count = retries["failures"].as_integer()
    due = retries["next_attempt_at"].as_string()
    return (or_(count.is_(None), count < MAX_FAILURES),
            or_(due.is_(None), due <= (now or now_utc()).isoformat()))


def unavailable(candidate, cached, now=None):
    now = now or now_utc()
    failures = cached.get("_llm_retry", {}).get("failures", 0) + 1
    exhausted = failures >= MAX_FAILURES
    candidate.article = {**candidate.article, "_llm_retry": {
        "failures": failures, "max_failures": MAX_FAILURES,
        "next_attempt_at": None if exhausted else (now + timedelta(hours=6 * 2 ** (failures - 1))).isoformat(),
    }}
    if exhausted:
        candidate.reason = "llm_retry_exhausted"
