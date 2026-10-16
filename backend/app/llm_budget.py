"""Durable provider quota windows; reserve input estimate + output cap before HTTP."""

from datetime import datetime, timedelta
from math import ceil
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .db import SchedulerCheckpoint, aware

PACIFIC = ZoneInfo("America/Los_Angeles")


class ProviderBudgetUnavailable(Exception):
    pass


def estimate_tokens(text):
    # Approximation, not a model tokenizer. Latin bytes/3 + 25%; other UTF-8
    # bytes counted individually. Always retain provider-reported actual usage.
    ascii_count = sum(ord(char) < 128 for char in text)
    return ceil((ascii_count / 3 + len(text.encode("utf-8")) - ascii_count) * 1.25)


def fit_prompt(system, user, cap, output_cap):
    system = " ".join(system.split())
    fixed = estimate_tokens(system) + 128  # Chat framing allowance.
    output = min(output_cap, cap - fixed - 128)
    if output < 256:
        raise ProviderBudgetUnavailable("prompt_exceeds_token_limit")
    available = cap - fixed - output
    lo, hi = 0, len(user)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(user[:mid]) <= available:
            lo = mid
        else:
            hi = mid - 1
    return system, user[:lo], fixed + estimate_tokens(user[:lo]) + output, output


def policies(settings):
    return {
        "groq": {
            "requests": settings.daily_groq_requests_per_day,
            "tokens": settings.daily_groq_tokens_per_day,
            "rpm": settings.groq_requests_per_minute,
            "tpm": settings.groq_tokens_per_minute,
            "request_tokens": settings.groq_tokens_per_request,
            "window": "rolling_24h",
        },
        "gemini": {
            "requests": settings.daily_gemini_requests_per_day,
            "tokens": settings.daily_gemini_tokens_per_day,
            "rpm": settings.gemini_requests_per_minute,
            "tpm": settings.gemini_tokens_per_minute,
            "request_tokens": 12000,
            "window": "America/Los_Angeles",
        },
    }


def cutoff(provider, now):
    return (
        now.astimezone(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
        if provider == "gemini"
        else now - timedelta(hours=24)
    )


def events_in_window(data, provider, now):
    return [
        event
        for event in data.get("events", [])
        if aware(datetime.fromisoformat(event["at"])) >= cutoff(provider, now)
    ]


def snapshot(data, provider, now):
    events = events_in_window(data, provider, now)
    policy = data.get("policy", {})
    usage = {"requests": len(events), "tokens": sum(event["tokens"] for event in events)}
    warnings = [key for key, value in usage.items() if policy.get(key, 0) > 0 and value >= policy[key] * 0.8]
    blocked = (
        data.get("blocked_reason", "")
        if data.get("blocked_until") and aware(datetime.fromisoformat(data["blocked_until"])) > now
        else ""
    )
    reset = (
        now.astimezone(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        if provider == "gemini"
        else min(
            (aware(datetime.fromisoformat(event["at"])) + timedelta(hours=24) for event in events),
            default=now + timedelta(hours=24),
        )
    )
    return {
        **usage,
        "limits": policy,
        "warnings": warnings,
        "blocked_reason": blocked,
        "timezone": "America/Los_Angeles" if provider == "gemini" else "rolling_24h",
        "reset_at": reset.isoformat(),
        "reported_tokens": sum(event.get("actual_tokens", 0) for event in events),
        "unconfirmed_attempts": sum("actual_tokens" not in event for event in events),
    }


def quota_status(session, now):
    result = {}
    for provider in ("gemini", "groq"):
        row = session.get(SchedulerCheckpoint, "llm_quota:" + provider)
        if row:
            result[provider] = snapshot(row.cursor, provider, now)
    return result


def legacy_reservations(session, provider, now, policy):
    # Upgrade conservatively from the request-only ledger. Unknown past token
    # usage stays charged at a full request reservation; never silently reset it.
    from .dates import TASHKENT
    from .free_budget import state_name

    day = now.astimezone(TASHKENT).date()
    events = []
    for age in range(3):
        row = session.get(SchedulerCheckpoint, state_name((day - timedelta(days=age)).isoformat()))
        for index, event in enumerate((row.cursor if row else {}).get("events", [])):
            if event["resource"] == "llm:" + provider:
                events.append(
                    {
                        "id": f"legacy:{age}:{index}",
                        "at": event["at"],
                        "tokens": policy["request_tokens"],
                        "reserved_tokens": policy["request_tokens"],
                    }
                )
    return sorted(events, key=lambda event: event["at"])


class ProviderQuotas:
    def __init__(self, budget, provider_policies):
        self.budget, self.policies = budget, provider_policies

    def blocked(self, provider):
        with self.budget.factory() as session:
            row = session.get(SchedulerCheckpoint, "llm_quota:" + provider)
            return snapshot(row.cursor, provider, self.budget.clock())["blocked_reason"] if row else None

    def block(self, provider, reason):
        now = self.budget.clock()
        with self.budget.factory.begin() as session:
            row = session.get(SchedulerCheckpoint, "llm_quota:" + provider)
            if row is None:
                row = SchedulerCheckpoint(name="llm_quota:" + provider, cursor={})
                session.add(row)
            until = (
                now.astimezone(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                if provider == "gemini"
                else now + timedelta(hours=24)
            )
            row.cursor = {
                **row.cursor,
                "policy": self.policies[provider],
                "blocked_reason": reason,
                "blocked_until": until.isoformat(),
            }

    def reserve(self, provider, tokens):
        budget, policy = self.budget, self.policies[provider]
        key = "llm:" + provider
        if budget.used[key] >= budget.limits[key][0]:
            raise ProviderBudgetUnavailable("run_limit:" + key)
        if tokens > min(policy["request_tokens"], policy["tpm"]):
            raise ProviderBudgetUnavailable("prompt_exceeds_token_limit")
        while True:
            budget.check()
            now = budget.clock()
            with budget.factory.begin() as session:
                row = session.scalar(
                    select(SchedulerCheckpoint)
                    .where(SchedulerCheckpoint.name == "llm_quota:" + provider)
                    .with_for_update()
                )
                if row is None:
                    row = SchedulerCheckpoint(
                        name="llm_quota:" + provider,
                        cursor={"events": legacy_reservations(session, provider, now, policy)},
                    )
                    session.add(row)
                data = row.cursor
                state = snapshot(data, provider, now)
                if state["blocked_reason"]:
                    raise ProviderBudgetUnavailable(state["blocked_reason"])
                events = events_in_window(data, provider, now)
                unavailable = (
                    state["requests"] >= policy["requests"] or state["tokens"] + tokens > policy["tokens"]
                )
                wait = 0
                if unavailable:
                    row.cursor = {
                        **data,
                        "policy": policy,
                        "blocked_reason": "daily_budget_exhausted",
                        "blocked_until": state["reset_at"],
                    }
                else:
                    recent = [
                        e
                        for e in data.get("events", [])
                        if aware(datetime.fromisoformat(e["at"])) > now - timedelta(seconds=60)
                    ]
                    if recent and (
                        len(recent) >= policy["rpm"]
                        or sum(e["reserved_tokens"] for e in recent) + tokens > policy["tpm"]
                    ):
                        wait = max(
                            0,
                            (
                                aware(datetime.fromisoformat(recent[0]["at"])) + timedelta(seconds=60.1) - now
                            ).total_seconds(),
                        )
                    if events:
                        wait = max(
                            wait,
                            budget.min_interval
                            - (now - aware(datetime.fromisoformat(events[-1]["at"]))).total_seconds(),
                        )
                    if wait <= 0:
                        identifier = uuid4().hex
                        event = {
                            "id": identifier,
                            "at": now.isoformat(),
                            "tokens": tokens,
                            "reserved_tokens": tokens,
                        }
                        retention_start = min(now - timedelta(hours=24), cutoff(provider, now))
                        retained = [
                            e
                            for e in data.get("events", [])
                            if aware(datetime.fromisoformat(e["at"])) >= retention_start
                        ]
                        row.cursor = {"events": [*retained, event], "policy": policy}
                        from .free_budget import state_name

                        daily = session.get(SchedulerCheckpoint, state_name(budget.day))
                        usage = dict(daily.cursor.get("usage", {}))
                        usage[key] = usage.get(key, 0) + 1
                        token_key = "tokens:" + provider
                        usage[token_key] = usage.get(token_key, 0) + tokens
                        daily.cursor = {
                            **daily.cursor,
                            "usage": usage,
                            "events": [
                                *daily.cursor.get("events", []),
                                {"at": now.isoformat(), "resource": key},
                                {
                                    "at": now.isoformat(),
                                    "resource": token_key,
                                    "amount": tokens,
                                    "reservation_id": identifier,
                                },
                            ][-2000:],
                        }
            if unavailable:
                raise ProviderBudgetUnavailable("daily_budget_exhausted")
            if wait > 0:
                from .telemetry import remaining, record
                if remaining(wait) < wait:
                    record("provider_waits", provider=provider, reason="minute_window", requested_seconds=round(wait, 2), skipped=True)
                    raise ProviderBudgetUnavailable("candidate_wait_exceeds_deadline")
                record("provider_waits", provider=provider, reason="minute_window", requested_seconds=round(wait, 2), skipped=False)
                budget.wait(wait)
                continue
            budget.used[key] += 1
            budget.used["tokens:" + provider] += tokens
            budget.events.append({"at": now.isoformat(), "resource": key})
            budget.events.append(
                {
                    "at": now.isoformat(),
                    "resource": "tokens:" + provider,
                    "amount": tokens,
                    "reservation_id": identifier,
                }
            )
            return identifier

    def reconcile(self, provider, identifier, usage):
        if (
            not isinstance(usage, dict)
            or not isinstance(usage.get("total_tokens"), int)
            or usage["total_tokens"] < 0
        ):
            return
        delta = 0
        with self.budget.factory.begin() as session:
            row = session.scalar(
                select(SchedulerCheckpoint)
                .where(SchedulerCheckpoint.name == "llm_quota:" + provider)
                .with_for_update()
            )
            events = [dict(event) for event in row.cursor.get("events", [])]
            for event in events:
                if event["id"] == identifier:
                    delta = usage["total_tokens"] - event["tokens"]
                    event["actual_tokens"] = usage["total_tokens"]
                    event["tokens"] = usage["total_tokens"]
                    event["reserved_tokens"] = max(event["reserved_tokens"], usage["total_tokens"])
                    event["usage"] = usage
                    from .free_budget import state_name

                    daily = session.get(SchedulerCheckpoint, state_name(self.budget.day))
                    counts = dict(daily.cursor.get("usage", {}))
                    counts["tokens:" + provider] = counts.get("tokens:" + provider, 0) + delta
                    daily_events = [dict(item) for item in daily.cursor.get("events", [])]
                    for item in daily_events:
                        if item.get("reservation_id") == identifier:
                            item["amount"] = usage["total_tokens"]
                    daily.cursor = {**daily.cursor, "usage": counts, "events": daily_events}
            row.cursor = {**row.cursor, "events": events}
        self.budget.used["tokens:" + provider] += delta
        for event in self.budget.events:
            if event.get("reservation_id") == identifier:
                event["amount"] = usage["total_tokens"]
