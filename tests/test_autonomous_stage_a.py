"""Offline contract checks for durable ingestion and provider fallback."""

import pytest
from sqlalchemy import select

from backend.app.db import Project, ProviderHealth, RawDiscovery
from backend.app.llm_service import LLMService, LLMUnavailable, ProviderFailure
from backend.app.raw_discovery import cheap_decision, ingest_raw, record_transition, recheck_obvious_noise
from backend.app.diagnostics import inspect_raw
from tests.conftest import sample_article


def test_raw_observation_is_idempotent_by_url_and_external_id(factory):
    with factory.begin() as session:
        first, created = ingest_raw(session, source_adapter="spot", source_url="https://news.example/a/",
                                    title="New project", raw_payload={"feed": "rss"})
        assert created and first.status == "pending"
        same, created = ingest_raw(session, source_adapter="spot", source_url="https://news.example/a")
        assert not created and same.id == first.id
        telegram, created = ingest_raw(session, source_adapter="telegram:channel", source_url="https://t.me/channel/42",
                                       external_id="42", raw_payload={"message_id": 42})
        assert created
        same, created = ingest_raw(session, source_adapter="telegram:channel", source_url="https://t.me/channel/42?x=1",
                                   external_id="42")
        assert not created and same.id == telegram.id
    with factory() as session:
        assert len(session.scalars(select(RawDiscovery)).all()) == 2


def test_cheap_filter_rejects_only_obvious_noise_and_records_history(factory):
    with factory.begin() as session:
        noise, _ = ingest_raw(session, source_adapter="spot", source_url="https://news.example/scholarship",
                              title="Student scholarship applications")
        possible, _ = ingest_raw(session, source_adapter="spot", source_url="https://news.example/demo-day",
                                 title="Demo Day teams presented products")
        scholarship_app, _ = ingest_raw(session, source_adapter="spot", source_url="https://news.example/scholarship-app",
                                        title="Scholarship app launched for students")
        unrelated, _ = ingest_raw(session, source_adapter="spot", source_url="https://news.example/nobel",
                                  title="Nobel literature winner announced")
        unrelated_uz, _ = ingest_raw(session, source_adapter="spot", source_url="https://news.example/nobel-uz",
                                     title="Adabiyot bo‘yicha Nobel mukofoti e’lon qilindi")
        assert cheap_decision(session, noise)[:2] == ("reject", "obvious_noise")
        assert cheap_decision(session, possible)[0] == "classify"
        assert cheap_decision(session, scholarship_app)[0] == "classify"
        assert cheap_decision(session, unrelated)[:2] == ("reject", "obvious_noise")
        assert cheap_decision(session, unrelated_uz)[:2] == ("reject", "obvious_noise")
        record_transition(noise, "rejected", "obvious_noise")
    with factory() as session:
        row = session.get(RawDiscovery, noise.id)
        assert row.status == "rejected" and row.processed_at and row.processing_history[-1]["reason"] == "obvious_noise"
        trace = inspect_raw(session, row.id)
        assert trace["reason"] == "obvious_noise" and trace["llm_attempt_count"] == 0


def test_recheck_noise_removes_only_obvious_review_without_project(factory):
    from backend.app.db import Candidate
    with factory.begin() as session:
        noise, _ = ingest_raw(session, source_adapter="news", source_url="https://news.example/nobel",
                              title="Nobel literature winner announced")
        possible, _ = ingest_raw(session, source_adapter="news", source_url="https://news.example/app",
                                 title="Scholarship app launched")
        record_transition(noise, "review_required", "llm_unavailable")
        record_transition(possible, "review_required", "llm_unavailable")
        session.add(Candidate(url=noise.source_url, article={}, status="review_required"))
        session.add(Candidate(url=possible.source_url, article={}, status="review_required"))
    assert recheck_obvious_noise(factory)["rejected_obvious_noise"] == 1
    with factory() as session:
        assert session.get(Candidate, noise.source_url).status == "rejected"
        assert session.get(Candidate, possible.source_url).status == "review_required"


class FakeProvider:
    configured = True
    model = "offline"
    def __init__(self, name, responses):
        self.name, self.responses, self.calls = name, list(responses), 0
    def complete(self, system, user, timeout):
        self.calls += 1
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.parametrize("provider_name", ["gemini", "openrouter", "groq"])
def test_each_provider_can_supply_validated_classification(settings, provider_name):
    provider = FakeProvider(provider_name, [{"classification": "NOT_PROJECT", "confidence": 0.91,
                                            "reason": "Saved source has no project"}])
    config = settings.model_copy(update={"llm_provider_order": provider_name})
    result = LLMService(config, providers={provider_name: provider}).analyze_source(sample_article())
    assert result.provider == provider_name and result.result.classification == "NOT_PROJECT"


def test_provider_chain_retries_and_falls_back_without_leaking_keys(settings, factory):
    first = FakeProvider("gemini", [ProviderFailure("invalid_json"), ProviderFailure("rate_limited")])
    second = FakeProvider("openrouter", [{"classification": "NOT_PROJECT", "confidence": 0.9,
                                          "reason": "scholarship announcement"}])
    config = settings.model_copy(update={"llm_provider_order": "gemini,openrouter", "llm_max_retries_per_provider": 1})
    service = LLMService(config, factory, {"gemini": first, "openrouter": second})
    analysis = service.analyze_source(sample_article())
    assert analysis.provider == "openrouter" and analysis.attempt_count == 3
    assert first.calls == 2 and second.calls == 1
    with factory() as session:
        health = session.get(ProviderHealth, "gemini")
        assert health.requests == 2 and health.invalid_json == 1 and health.rate_limits == 1
        assert health.fallback_count == 1
    assert "Bearer" not in repr(service.status())


def test_circuit_breaker_skips_failed_provider_within_window(settings):
    first = FakeProvider("gemini", [ProviderFailure("provider_error")])
    second = FakeProvider("groq", [{"classification": "NOT_PROJECT", "confidence": 0.8,
                                    "reason": "market overview"}])
    config = settings.model_copy(update={"llm_provider_order": "gemini,groq",
                                 "llm_max_retries_per_provider": 0, "llm_circuit_breaker_failures": 1})
    service = LLMService(config, providers={"gemini": first, "groq": second})
    assert service.analyze_source(sample_article()).provider == "groq"
    second.responses.append({"classification": "NOT_PROJECT", "confidence": 0.8, "reason": "market overview"})
    assert service.analyze_source(sample_article()).provider == "groq"
    assert first.calls == 1


def test_all_providers_fail_and_project_rows_survive_migration(settings, factory):
    first = FakeProvider("gemini", [ProviderFailure("quota_exceeded")])
    config = settings.model_copy(update={"llm_provider_order": "gemini", "llm_max_retries_per_provider": 0})
    service = LLMService(config, factory, {"gemini": first})
    try:
        service.analyze_source(sample_article())
        assert False, "expected fallback"
    except LLMUnavailable as exc:
        assert exc.code == "llm_unavailable"
    with factory() as session:
        assert session.scalars(select(Project)).all() == []
