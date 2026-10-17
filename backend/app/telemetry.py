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
    if trace is None or trace.get("finishing_decision"):
        return default
    from .network import CandidateTimeout

    left = trace["deadline"] - monotonic()
    if left <= 0:
        raise CandidateTimeout("candidate_timeout")
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
        "timings_ms": dict.fromkeys(("robots", "page_read", "extraction", "llm", "pauses", "lock_wait", "db_sql", "db_transaction", "db_checkout", "db_connect", "quota_before_http", "quota_after_http", "validation", "provider_window_wait", "validated_checkpoint", "decision_write", "lease"), 0),
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

# Aggregate SQL/transaction metadata without recording SQL text or parameters.
RUN_TRACE = ContextVar("run_trace", default=None)
DB_COMPONENT = ContextVar("db_component", default="general")


def db_record(kind, elapsed_ms):
    for trace in (ACTIVE_TRACE.get(), RUN_TRACE.get()):
        if trace is None:
            continue
        stats = trace.setdefault("database", {"sql_queries": 0, "commits": 0, "rollbacks": 0, "checkout_probes": 0, "elapsed_ms": 0, "by_component": {}})
        stats[kind] = stats.get(kind, 0) + 1
        stats["elapsed_ms"] = round(stats["elapsed_ms"] + elapsed_ms, 2)
        part = stats["by_component"].setdefault(DB_COMPONENT.get(), {"sql_queries": 0, "elapsed_ms": 0})
        if kind == "sql_queries":
            part["sql_queries"] += 1
        part["elapsed_ms"] = round(part["elapsed_ms"] + elapsed_ms, 2)


@contextmanager
def db_work(component):
    token = DB_COMPONENT.set(component)
    try:
        with span(component):
            yield
    finally:
        DB_COMPONENT.reset(token)


@contextmanager
def finishing_decision():
    trace = ACTIVE_TRACE.get()
    old = trace.get("finishing_decision", False) if trace else False
    if trace is not None:
        trace["finishing_decision"] = True
    try:
        with db_work("decision_write"):
            yield
    finally:
        if trace is not None:
            trace["finishing_decision"] = old


@contextmanager
def phase(name):
    trace = RUN_TRACE.get()
    began = monotonic()
    frame = {"nested": 0, "began": began, "name": name}
    if trace is not None:
        trace.setdefault("_phases", []).append(frame)
    try:
        yield
    finally:
        elapsed = monotonic() - began
        if trace is not None:
            trace["_phases"].pop()
            if trace["_phases"]:
                trace["_phases"][-1]["nested"] += elapsed
            phases = trace.setdefault("phases_ms", {})
            phases[name] = round(phases.get(name, 0) + (elapsed - frame["nested"]) * 1000, 2)


def instrument_database(engine):
    from sqlalchemy import event
    @event.listens_for(engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, many):
        context._diagnostic_begin = monotonic()
        context._diagnostic_span = span("db_sql")
        context._diagnostic_span.__enter__()
    def finish(context):
        began = getattr(context, "_diagnostic_begin", None)
        if began is not None:
            context._diagnostic_begin = None
            context._diagnostic_span.__exit__(None, None, None)
            db_record("sql_queries", (monotonic() - began) * 1000)
    @event.listens_for(engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, many):
        finish(context)
    @event.listens_for(engine, "handle_error")
    def error(context):
        if context.execution_context is not None:
            finish(context.execution_context)
    @event.listens_for(engine, "do_connect")
    def connect(dialect, record, args, kwargs):
        began = monotonic()
        try:
            with span("db_connect"):
                return dialect.connect(*args, **kwargs)
        finally:
            db_record("connections", (monotonic() - began) * 1000)

    for method, kind in (("do_commit", "commits"), ("do_rollback", "rollbacks")):
        original = getattr(engine.dialect, method)
        def wrapped(connection, _original=original, _kind=kind):
            began = monotonic()
            try:
                with span("db_transaction"):
                    return _original(connection)
            finally:
                db_record(_kind, (monotonic() - began) * 1000)
        setattr(engine.dialect, method, wrapped)


def phase_snapshot(trace):
    result = dict(trace.get("phases_ms", {}))
    now = monotonic()
    stack = trace.get("_phases", [])
    for index, frame in enumerate(stack):
        active_child = now - stack[index + 1]["began"] if index + 1 < len(stack) else 0
        value = (now - frame["began"] - frame["nested"] - active_child) * 1000
        result[frame["name"]] = round(result.get(frame["name"], 0) + max(0, value), 2)
    result["total"] = round((now - trace.get("began", now)) * 1000, 2)
    return result
