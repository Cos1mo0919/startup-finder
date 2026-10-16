"""Allowlisted diagnostics only: never source text, prompts, headers or query strings."""

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

ACTIVE_TRACE = ContextVar("candidate_trace", default=None)


def record(category, **fields):
    trace = ACTIVE_TRACE.get()
    if trace is not None:
        trace.setdefault(category, []).append(fields)


def remaining(default):
    trace = ACTIVE_TRACE.get()
    if trace is None:
        return default
    from .network import FetchError

    left = trace["deadline"] - monotonic()
    if left <= 0:
        raise FetchError("candidate_timeout")
    return min(default, left)


@contextmanager
def span(stage):
    began = monotonic()
    trace = ACTIVE_TRACE.get()
    frame = {"nested": 0.0}
    if trace is not None:
        trace.setdefault("_spans", []).append(frame)
    try:
        yield
    finally:
        elapsed = monotonic() - began
        if trace is not None:
            trace["_spans"].pop()
            if trace["_spans"]:
                trace["_spans"][-1]["nested"] += elapsed
            timings = trace["timings_ms"]
            timings[stage] = round(timings.get(stage, 0) + (elapsed - frame["nested"]) * 1000, 2)


@contextmanager
def candidate_trace(seconds=60):
    began = monotonic()
    trace = {
        "timings_ms": dict.fromkeys(("robots", "page_read", "extraction", "llm", "pauses", "lock_wait"), 0),
        "provider_attempts": [],
        "fetch": [],
        "extraction": [],
        "deadline": began + seconds,
    }
    token = ACTIVE_TRACE.set(trace)
    try:
        yield trace
    finally:
        trace["timings_ms"]["total"] = round((monotonic() - began) * 1000, 2)
        trace.pop("deadline", None)
        trace.pop("_spans", None)
        trace["timings_ms"]["other"] = round(
            max(
                0,
                trace["timings_ms"]["total"]
                - sum(value for key, value in trace["timings_ms"].items() if key != "total"),
            ),
            2,
        )
        ACTIVE_TRACE.reset(token)
