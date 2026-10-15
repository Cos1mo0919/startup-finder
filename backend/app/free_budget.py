"""Crash-safe daily counters. Reservations commit BEFORE an external request."""

from collections import Counter
from contextvars import ContextVar
from datetime import timedelta
from time import monotonic, sleep
import resource as process_resource

from sqlalchemy import select, text

from .db import SchedulerCheckpoint, aware, now_utc
from .dates import TASHKENT

ACTIVE = ContextVar("izlanish_free_budget", default=None)


class BudgetStop(Exception):
    pass


def current_budget():
    return ACTIVE.get()


def state_name(day):
    return "free_daily:" + day


class DailyBudget:
    def __init__(self, factory, limits, target, seconds, run_id, clock=now_utc, timer=monotonic,
                 min_interval=60, output_tokens=2048, max_database_bytes=250_000_000, max_rss_mb=384,
                 provider_policies=None, page_mode=None):
        self.factory, self.limits, self.target = factory, limits, target
        self.clock, self.timer, self.deadline = clock, timer, timer() + seconds
        self.day = clock().astimezone(TASHKENT).date().isoformat()
        self.run_id, self.used, self.events = run_id, Counter(), []
        self.min_interval, self.output_tokens = min_interval, output_tokens
        self.max_database_bytes, self.max_rss_mb = max_database_bytes, max_rss_mb
        self.stop_reason = ""
        from .llm_budget import ProviderQuotas
        self.quotas = ProviderQuotas(self, provider_policies) if provider_policies else None
        self.request_output_tokens = output_tokens
        with factory.begin() as session:
            row = session.get(SchedulerCheckpoint, state_name(self.day))
            if row is None:
                row = SchedulerCheckpoint(name=state_name(self.day), cursor={"usage": {}, "blocked": {}})
                session.add(row)
            row.cursor = {**row.cursor, "limits": limits, "target": target}
        from .page_budget import PageBudget
        self.pages = PageBudget(self, page_mode) if page_mode else None

    def resource_key(self, resource):
        return self.pages.key if resource == "pages" and self.pages else state_name(self.day)

    def stop(self, reason):
        self.stop_reason = reason
        raise BudgetStop(reason)

    def check_time(self):
        if self.stop_reason:
            raise BudgetStop(self.stop_reason)
        if self.timer() >= self.deadline:
            self.stop("max_run_seconds")
        if self.clock().astimezone(TASHKENT).date().isoformat() != self.day:
            self.stop("calendar_day_changed")

    def check(self, enforce_caps=True):
        self.check_time()
        from .writer import renew_writer
        renew_writer(self.factory)
        if process_resource.getrusage(process_resource.RUSAGE_SELF).ru_maxrss >= self.max_rss_mb * 1024:
            self.stop("memory_guard")
        from .db import DailyStats
        with self.factory() as session:
            if session.bind.dialect.name == "postgresql":
                size = session.scalar(text("SELECT pg_database_size(current_database())"))
            else:
                size = session.scalar(text("PRAGMA page_count")) * session.scalar(text("PRAGMA page_size"))
            if size >= self.max_database_bytes:
                self.stop("database_size_guard")
            today = session.get(DailyStats, self.day)
            if today and today.published_count >= self.target:
                self.stop("daily_project_target")
            state = session.get(SchedulerCheckpoint, state_name(self.day)).cursor
            if enforce_caps:
                for key, (run_cap, day_cap) in self.limits.items():
                    if key == "pages" and self.pages:
                        page_row = session.get(SchedulerCheckpoint, self.pages.key)
                        spent = page_row.cursor.get("usage", {}).get("pages", 0)
                    else:
                        spent = state.get("usage", {}).get(key, 0)
                    if self.quotas and key.startswith("llm:"):
                        continue  # Provider windows differ from the publication day.
                    provider = key.removeprefix("llm:")
                    if state.get("blocked", {}).get(provider):
                        continue
                    if run_cap > 0 and self.used[key] >= run_cap:
                        self.stop("run_limit:" + key)
                    if day_cap > 0 and spent >= day_cap:
                        self.stop("daily_limit:" + key)

    def blocked(self, provider):
        if self.quotas and provider in self.quotas.policies:
            return self.quotas.blocked(provider)
        with self.factory() as session:
            state = session.get(SchedulerCheckpoint, state_name(self.day)).cursor
            return (state.get("blocked") or {}).get(provider)

    def block(self, provider, reason):
        if self.quotas and provider in self.quotas.policies:
            return self.quotas.block(provider, reason)
        with self.factory.begin() as session:
            row = session.scalar(select(SchedulerCheckpoint).where(
                SchedulerCheckpoint.name == state_name(self.day)).with_for_update())
            row.cursor = {**row.cursor, "blocked": {**row.cursor.get("blocked", {}), provider: reason}}

    def wait(self, seconds):
        while seconds > 0:
            self.check_time()
            from .writer import renew_writer
            renew_writer(self.factory)
            chunk = min(seconds, 30, max(0, self.deadline - self.timer()))
            if chunk <= 0:
                self.stop("max_run_seconds")
            sleep(chunk)
            seconds -= chunk
        self.check_time()

    def reserve_many(self, resources):
        self.check()
        for resource in resources:
            self.reserve(resource, grouped=True)

    def reserve(self, resource, grouped=False):
        self.check(enforce_caps=not grouped)
        run_limit, day_limit = self.limits[resource]
        if self.used[resource] >= run_limit:
            self.stop("run_limit:" + resource)
        with self.factory() as session:
            state = session.get(SchedulerCheckpoint, self.resource_key(resource)).cursor
            if state.get("usage", {}).get(resource, 0) >= day_limit:
                self.stop("daily_limit:" + resource)
        if resource.startswith("llm:"):
            with self.factory() as session:
                previous = session.get(SchedulerCheckpoint, self.resource_key(resource)).cursor.get("last_requests", {}).get(resource)
            if previous:
                from datetime import datetime
                wait = self.min_interval - (self.clock() - aware(datetime.fromisoformat(previous))).total_seconds()
                if wait > 0:
                    sleep(min(wait, max(0, self.deadline - self.timer())))
                    self.check()
        with self.factory.begin() as session:
            row = session.scalar(select(SchedulerCheckpoint).where(
                SchedulerCheckpoint.name == self.resource_key(resource)).with_for_update())
            usage = dict(row.cursor.get("usage", {}))
            if usage.get(resource, 0) >= day_limit:
                self.stop("daily_limit:" + resource)
            usage[resource] = usage.get(resource, 0) + 1
            page_fields = {}
            if resource == "pages" and self.pages:
                key = str(self.run_id)
                page_fields = {"charges": {**row.cursor.get("charges", {}), key: row.cursor.get("charges", {}).get(key, 0) + 1},
                               "attempts": {**row.cursor.get("attempts", {}), key: row.cursor.get("attempts", {}).get(key, 0) + 1}}
            row.cursor = {**row.cursor, "usage": usage, "limits": self.limits, "target": self.target,
                          **page_fields,
                          "last_requests": {**row.cursor.get("last_requests", {}), resource: self.clock().isoformat()},
                          "events": [*row.cursor.get("events", []), {"at": self.clock().isoformat(), "resource": resource}][-2000:]}
            row.last_attempt_at = self.clock()
        self.used[resource] += 1
        self.events.append({"at": self.clock().isoformat(), "resource": resource})
        # No URLs, prompts, payloads or credentials are written to budget logs.
        from .db import Run
        with self.factory.begin() as session:
            row = session.get(Run, self.run_id)
            if row:
                row.details = {**row.details, "usage": dict(self.used), "budget_events": self.events}


def free_status(session, settings):
    from .db import Run, DailyStats, RawDiscovery
    from sqlalchemy import func
    now = now_utc()
    day = now.astimezone(TASHKENT).date().isoformat()
    state = session.get(SchedulerCheckpoint, state_name(day))
    data = state.cursor if state else {}
    usage = data.get("usage", {})
    limits = data.get("limits", {})
    rows = session.scalars(select(Run).where(Run.started_at >= now - timedelta(hours=24),
                           Run.details["mode"].as_string() == "free_daily")
                           .order_by(Run.id.desc()).limit(100)).all()
    runs = [row for row in rows if (row.details or {}).get("mode") == "free_daily"]
    recent = Counter()
    yesterday = (now.astimezone(TASHKENT).date() - timedelta(days=1)).isoformat()
    prior = session.get(SchedulerCheckpoint, state_name(yesterday))
    for checkpoint in [prior, state]:
        for event in (checkpoint.cursor if checkpoint else {}).get("events", []):
            from datetime import datetime
            if aware(datetime.fromisoformat(event["at"])) >= now - timedelta(hours=24):
                recent[event["resource"]] += event.get("amount", 1)
    # Physical page attempts remain visible even when their local allowance was
    # refunded; use the per-run audit so trial/daily ledgers cannot double count.
    from datetime import datetime
    recent["pages"] = sum(1 for run in runs for event in run.details.get("budget_events", [])
                          if event.get("resource") == "pages"
                          and aware(datetime.fromisoformat(event["at"])) >= now - timedelta(hours=24))
    today = session.get(DailyStats, day)
    from .llm_budget import quota_status
    provider_quotas = quota_status(session, now)
    from .page_budget import page_key
    page_budgets = {}
    for mode in ("trial", "daily"):
        page_row = session.get(SchedulerCheckpoint, page_key(day, mode))
        if page_row:
            page_budgets[mode] = {"used": page_row.cursor.get("usage", {}).get("pages", 0),
                                 "limits": page_row.cursor.get("page_limits", [0, 0]),
                                 "attempted": sum(page_row.cursor.get("attempts", {}).values()),
                                 "refunded": sum(page_row.cursor.get("refunds", {}).values())}
    selected_mode = data.get("page_mode") or ("trial" if runs and runs[0].details.get("trial") else "daily")
    if selected_mode in page_budgets:
        usage = {**usage, "pages": page_budgets[selected_mode]["used"]}
        limits = {**limits, "pages": page_budgets[selected_mode]["limits"]}
    limits = {key: value for key, value in limits.items()
              if not (key.startswith("llm:") and key.removeprefix("llm:") in provider_quotas)}
    # Rolling 24h metrics use the provider ledger across publication midnights.
    for provider in provider_quotas:
        row = session.get(SchedulerCheckpoint, "llm_quota:" + provider)
        from datetime import datetime
        events = [event for event in row.cursor.get("events", [])
                  if aware(datetime.fromisoformat(event["at"])) >= now - timedelta(hours=24)]
        recent["llm:" + provider] = len(events)
        recent["tokens:" + provider] = sum(event["tokens"] for event in events)
    return {"day": day, "timezone": "Asia/Tashkent", "target": data.get("target", settings.daily_project_target),
            "published_today": today.published_count if today else 0,
            "usage_today": usage, "usage_24h": dict(recent), "limits": limits,
            "blocked_providers": {**{name: reason for name, reason in data.get("blocked", {}).items()
                                     if name not in provider_quotas},
                                  **{name: value["blocked_reason"] for name, value in provider_quotas.items()
                                     if value["blocked_reason"]}},
            "providers_enabled": data.get("providers_enabled", {}),
            "provider_quotas": provider_quotas,
            "page_mode": selected_mode, "page_budgets": page_budgets,
            "warnings": [key for key, value in usage.items()
                         if limits.get(key, [0, 0])[1] > 0 and value >= limits[key][1] * 0.8],
            "last_run": {"id": runs[0].id, "status": runs[0].status,
                         "stop_reason": runs[0].details.get("stop_reason", "running")} if runs else None,
            "found_24h": session.scalar(select(func.count()).select_from(RawDiscovery).where(
                RawDiscovery.discovered_at >= now - timedelta(hours=24),
                RawDiscovery.raw_payload["free_daily_run_id"].as_integer().is_not(None))) or 0,
            "published_24h": recent.get("published", 0)}
