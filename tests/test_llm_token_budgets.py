"""No live providers or production DB: persisted token/rate budgets and clock windows."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.app.catalog import PROMPT_PATH
from backend.app.free_budget import ACTIVE, free_status
from backend.app.free_daily import profile
from backend.app.llm_budget import ProviderBudgetUnavailable, fit_prompt, policies, quota_status
from backend.app.llm_service import GeminiProvider, GroqProvider, LLMService, ProviderFailure
from tests.test_free_daily import make_budget
from tests.test_autonomous_stage_a import FakeProvider


def managed(settings, factory, **kwargs):
    config, limits, _ = profile(settings)
    limits.update({"llm:gemini": (20, 250), "llm:groq": (20, 500)})
    policy = policies(config)
    policy.update(kwargs.pop("policy", {}))
    return make_budget(factory, limits=limits, provider_policies=policy, **kwargs)


def test_token_reservation_survives_restart_and_actual_reconciles(settings, factory):
    budget = managed(settings, factory)
    identifier = budget.quotas.reserve("groq", 5500)
    with factory() as session:
        assert quota_status(session, budget.clock())["groq"]["tokens"] == 5500
    budget.quotas.reconcile(
        "groq", identifier, {"total_tokens": 2200, "prompt_tokens": 1200, "completion_tokens": 1000}
    )
    again = managed(settings, factory)
    with factory() as session:
        status = quota_status(session, again.clock())["groq"]
        assert status["tokens"] == status["reported_tokens"] == 2200
        assert status["requests"] == 1 and status["unconfirmed_attempts"] == 0
        assert free_status(session, settings)["usage_today"]["tokens:groq"] == 2200


def test_token_budget_rejects_before_http_and_fallback_remains_possible(settings, factory):
    budget = managed(settings, factory)
    budget.quotas.policies["groq"]["tokens"] = 6000
    budget.quotas.reserve("groq", 5500)
    with pytest.raises(ProviderBudgetUnavailable, match="daily_budget_exhausted"):
        budget.quotas.reserve("groq", 5500)
    assert budget.blocked("groq") == "daily_budget_exhausted"
    assert not budget.blocked("gemini")
    budget.quotas.reserve("gemini", 1000)
    with factory() as session:
        assert quota_status(session, budget.clock())["groq"]["requests"] == 1


def test_request_budget_and_80_percent_warning(settings, factory):
    budget = managed(settings, factory)
    budget.quotas.policies["gemini"]["requests"] = 1
    budget.quotas.reserve("gemini", 1000)
    with factory() as session:
        assert "requests" in quota_status(session, budget.clock())["gemini"]["warnings"]
    with pytest.raises(ProviderBudgetUnavailable):
        budget.quotas.reserve("gemini", 1000)
    assert budget.blocked("gemini") == "daily_budget_exhausted"


def test_groq_tokens_minute_window_and_restart(settings, factory):
    clock = [datetime(2026, 10, 15, 10, tzinfo=timezone.utc)]
    budget = managed(settings, factory, clock=lambda: clock[0])
    budget.quotas.reserve("groq", 5500)
    again = managed(settings, factory, clock=lambda: clock[0])
    waits = []

    def wait(seconds):
        waits.append(seconds)
        clock[0] += timedelta(seconds=seconds)

    again.wait = wait
    again.quotas.reserve("groq", 5500)
    assert len(waits) == 1 and waits[0] >= 60
    with factory() as session:
        assert quota_status(session, clock[0])["groq"]["tokens"] == 11000


def test_gemini_ten_requests_per_rolling_minute(settings, factory):
    clock = [datetime(2026, 10, 15, 10, tzinfo=timezone.utc)]
    budget = managed(settings, factory, clock=lambda: clock[0])
    for _ in range(10):
        budget.quotas.reserve("gemini", 100)
    waits = []

    def wait(seconds):
        waits.append(seconds)
        clock[0] += timedelta(seconds=seconds)

    budget.wait = wait
    budget.quotas.reserve("gemini", 100)
    assert waits[0] >= 60


@pytest.mark.parametrize(
    "instant,seconds", [("2026-07-15T06:59:59+00:00", 1), ("2026-12-15T07:59:59+00:00", 1)]
)
def test_gemini_resets_at_pacific_midnight_with_dst(settings, factory, instant, seconds):
    clock = [datetime.fromisoformat(instant)]
    budget = managed(settings, factory, clock=lambda: clock[0])
    budget.quotas.policies["gemini"]["requests"] = 1
    budget.quotas.reserve("gemini", 100)
    with pytest.raises(ProviderBudgetUnavailable):
        budget.quotas.reserve("gemini", 100)
    # Tashkent day does not change here; only provider window changes.
    clock[0] += timedelta(seconds=seconds)
    assert not budget.blocked("gemini")
    budget.quotas.reserve("gemini", 100)
    with factory() as session:
        assert quota_status(session, clock[0])["gemini"]["requests"] == 1


def test_groq_does_not_reset_at_tashkent_midnight(settings, factory):
    clock = [datetime(2026, 10, 15, 18, 59, tzinfo=timezone.utc)]
    first = managed(settings, factory, clock=lambda: clock[0])
    first.quotas.reserve("groq", 5500)
    clock[0] += timedelta(minutes=2)
    managed(settings, factory, clock=lambda: clock[0])
    with factory() as session:
        assert quota_status(session, clock[0])["groq"]["tokens"] == 5500
    clock[0] += timedelta(hours=24)
    with factory() as session:
        assert quota_status(session, clock[0])["groq"]["tokens"] == 0


def test_prompt_fits_without_mutating_source_or_dropping_rules():
    system, article = PROMPT_PATH.read_text(), "Text of a real product. " * 2000
    reduced, user, tokens, output = fit_prompt(system, article, 5500, 2048)
    assert tokens <= 5500 and len(user) < len(article) and 256 <= output <= 1024
    assert reduced.split() == system.split()
    with pytest.raises(ProviderBudgetUnavailable):
        fit_prompt("x" * 30000, article, 5500, 2048)


def test_rate_limit_retries_then_fallback_and_day_block(settings, factory):
    budget = managed(settings, factory)
    clock = [budget.clock()]
    budget.clock = lambda: clock[0]
    waits = []

    def wait(seconds):
        waits.append(seconds)
        clock[0] += timedelta(seconds=seconds)

    budget.wait = wait
    gemini = FakeProvider("gemini", [ProviderFailure("rate_limited")] * 3)
    groq = FakeProvider("groq", [{"ok": True}])
    config = settings.model_copy(update={"llm_provider_order": "gemini,groq"})
    token = ACTIVE.set(budget)
    try:
        result = LLMService(config, factory, {"gemini": gemini, "groq": groq}).analyze_json(
            "Rules", "source", lambda value: value
        )
    finally:
        ACTIVE.reset(token)
    assert result.provider == "groq" and result.attempt_count == 4
    assert gemini.calls == 3 and groq.calls == 1
    assert waits == [15, 30]
    assert budget.blocked("gemini") == "rate_limited"
    with factory() as session:
        assert quota_status(session, clock[0])["gemini"]["requests"] == 3


def test_retry_after_is_respected_and_success_keeps_provider_enabled(settings, factory):
    budget = managed(settings, factory)
    clock = [budget.clock()]
    budget.clock = lambda: clock[0]
    waits = []

    def wait(seconds):
        waits.append(seconds)
        clock[0] += timedelta(seconds=seconds)

    budget.wait = wait
    provider = FakeProvider("gemini", [ProviderFailure("rate_limited", 25), {"ok": True}])
    token = ACTIVE.set(budget)
    try:
        LLMService(
            settings.model_copy(update={"llm_provider_order": "gemini"}), factory, {"gemini": provider}
        ).analyze_json("Rules", "source", lambda x: x)
    finally:
        ACTIVE.reset(token)
    assert waits == [25] and not budget.blocked("gemini")


def test_actual_usage_captured_by_both_http_adapters_and_output_is_bounded(monkeypatch, settings, factory):
    monkeypatch.setattr("backend.app.llm_service.public_dns", lambda *args: None)
    budget = managed(settings, factory)

    def reply(request):
        import json

        body = json.loads(request.content)
        if "groq" in request.url.host:
            assert body["max_tokens"] == 1024
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": '{"ok":true}'}}],
                    "usage": {"total_tokens": 321, "prompt_tokens": 200, "completion_tokens": 121},
                },
            )
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}],
                "usageMetadata": {"totalTokenCount": 222},
            },
        )

    token = ACTIVE.set(budget)
    try:
        budget.request_output_tokens = 1024
        for provider in [
            GroqProvider("test", "openai/gpt-oss-20b", httpx.Client(transport=httpx.MockTransport(reply))),
            GeminiProvider(
                "test", "gemini-3.1-flash-lite", httpx.Client(transport=httpx.MockTransport(reply))
            ),
        ]:
            provider.complete("Rules", "text", 1)
            assert provider.last_usage["total_tokens"] in (321, 222)
    finally:
        ACTIVE.reset(token)
    assert not GeminiProvider("key", "gemini-3.8-flash").configured
    assert not GeminiProvider("key", "gemini-3-flash").configured
    assert (
        profile(settings.model_copy(update={"gemini_model": "gemini-3.8-flash"}))[0].gemini_model
        == "gemini-3.1-flash-lite"
    )


def test_token_eighty_percent_warning_is_visible_to_admin(settings, factory):
    budget = managed(settings, factory)
    for index in range(16):
        budget.quotas.reserve("groq", 5000)
        # Advance rate window without spending wall-clock time.
        previous = budget.clock()
        budget.clock = lambda previous=previous: previous + timedelta(seconds=61)
    with factory() as session:
        status = free_status(session, settings)
        assert status["provider_quotas"]["groq"]["tokens"] == 80000
        assert status["provider_quotas"]["groq"]["warnings"] == ["tokens"]


def test_upgrade_preserves_old_request_only_spend(settings, factory):
    from backend.app.free_budget import state_name
    from backend.app.db import SchedulerCheckpoint

    old = make_budget(factory)
    old.reserve("llm:groq")
    new = managed(settings, factory, clock=lambda: old.clock() + timedelta(seconds=61))
    new.quotas.reserve("groq", 5500)
    with factory() as session:
        quota = quota_status(session, new.clock())["groq"]
        assert quota["requests"] == 2 and quota["tokens"] == 11000
        assert session.get(SchedulerCheckpoint, state_name(new.day)).cursor["usage"]["llm:groq"] == 2


def test_preflight_budget_exhaustion_falls_back_without_first_provider_http(settings, factory):
    budget = managed(settings, factory)
    budget.quotas.policies["groq"]["tokens"] = 1
    groq = FakeProvider("groq", [])
    gemini = FakeProvider("gemini", [{"ok": True}])
    token = ACTIVE.set(budget)
    try:
        result = LLMService(
            settings.model_copy(update={"llm_provider_order": "groq,gemini"}),
            factory,
            {"groq": groq, "gemini": gemini},
        ).analyze_json("Rules", "source", lambda x: x)
    finally:
        ACTIVE.reset(token)
    assert groq.calls == 0 and result.provider == "gemini"


def test_fall_dst_twenty_five_hour_gemini_day_keeps_its_first_hour(settings, factory):
    early = datetime(2026, 11, 1, 7, tzinfo=timezone.utc)
    budget = managed(settings, factory, clock=lambda: early)
    budget.quotas.reserve("gemini", 100)
    late = early + timedelta(hours=24, minutes=30)
    next_job = managed(settings, factory, clock=lambda: late)
    next_job.quotas.reserve("gemini", 100)
    with factory() as session:
        assert quota_status(session, late)["gemini"]["requests"] == 2


def test_trial_run_cap_does_not_replace_global_provider_day_cap(settings):
    config, limits, _ = profile(settings, trial=True)
    policy = policies(config)
    assert limits["llm:gemini"][0] == limits["llm:groq"][0] == 5
    assert policy["gemini"]["requests"] == 250 and policy["groq"]["requests"] == 500
