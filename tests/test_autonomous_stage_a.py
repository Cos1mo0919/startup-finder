"""Offline contract checks for durable ingestion and provider fallback."""

from sqlalchemy import select

from backend.app.db import Project, ProviderHealth, RawDiscovery
from backend.app.llm_service import LLMService, LLMUnavailable, ProviderFailure
from backend.app.raw_discovery import cheap_decision, ingest_raw, record_transition
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
        assert cheap_decision(session, noise)[:2] == ("reject", "obvious_noise")
        assert cheap_decision(session, possible)[0] == "classify"
        record_transition(noise, "rejected", "obvious_noise")
    with factory() as session:
        row = session.get(RawDiscovery, noise.id)
        assert row.status == "rejected" and row.processed_at and row.processing_history[-1]["reason"] == "obvious_noise"


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
