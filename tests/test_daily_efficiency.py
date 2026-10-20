"""Offline quota-stop, delayed reviews and remote-database cost regressions."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.catalog import ClassifierFailure, parse_classifier_response
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.connection_pool import clean_postgres_checkout
from backend.app.db import Candidate, Run, RegistrySource, now_utc
from backend.app.free_daily import run_daily, next_candidate
from backend.app.llm_service import LLMService, LLMUnavailable
from backend.app.source_yield import recent_yield
from backend.app.telemetry import candidate_trace
from tests.conftest import FakeDiscovery, sample_article
from tests.test_autonomous_stage_a import FakeProvider
from tests.test_catalog_v31 import project_payload
from tests.test_connection_hygiene import Connection
from tests.test_daily_postgres import postgres_factory  # noqa:F401


def configured(settings):
    return settings.model_copy(update={"free_provider_quotas_confirmed": True,
        "gemini_api_key": SecretStr("offline"), "groq_api_key": SecretStr("offline"),
        "daily_gemini_requests_per_run": 1, "daily_groq_requests_per_run": 1,
        "daily_llm_min_interval_seconds": 0})


@pytest.mark.parametrize("db_fixture", ["factory", "postgres_factory"])
def test_exhausted_llm_run_budget_stops_before_selection_or_candidate_charge(settings, request, db_fixture):
    factory = request.getfixturevalue(db_fixture)
    with factory.begin() as session:
        for i in range(5):
            article = sample_article(url=f"https://fixture.example/project-{i}")
            session.add(Candidate(url=article.url, status="queued", article=article.model_dump(mode="json")))
    payload = {"classification": "NOT_PROJECT", "confidence": 0.95, "reason": "Market overview"}
    providers = {name: FakeProvider(name, [payload] * 5) for name in ("gemini", "groq")}

    def pipeline(config, factory):
        return CatalogPipeline(config, factory, FakeDiscovery([]), llm_service=LLMService(config, factory, providers))

    result = run_daily(configured(settings), factory, trial=True, pipeline_factory=pipeline)
    assert result["stop_reason"] == "llm_run_budget_reached", result
    assert result["counts"]["attempted"] == result["usage"]["candidates"] == 2
    assert result["counts"]["review_required"] == 0
    assert [p.calls for p in providers.values()] == [1, 1]
    assert result["run_database"]["select_1_ms"] >= 0
    assert result["run_database"]["average_query_ms"] >= 0
    with factory() as session:
        assert len(list(session.scalars(select(Candidate).where(Candidate.status == "queued")))) == 3
        assert all(row.attempts == 0 for row in session.scalars(select(Candidate).where(Candidate.status == "queued")))


@pytest.mark.parametrize("db_fixture", ["factory", "postgres_factory"])
def test_unavailable_reviews_retry_after_delay_with_priority_and_eventually_stop(settings, request, db_fixture):
    factory = request.getfixturevalue(db_fixture)
    article = sample_article()
    with factory.begin() as session:
        session.add(Candidate(url=article.url, status="review_required", reason="llm_unavailable",
            updated_at=now_utc() - timedelta(hours=7), article=article.model_dump(mode="json")))
        session.add(Candidate(url="https://other.example/new", status="queued", article={"_queued": True}))
    assert next_candidate(factory, set(), True) == article.url

    class Unavailable:
        available = operational = True
        last_attempt_count = 0
        def analyze_source(self, article):
            raise LLMUnavailable("llm_unavailable")
        def status(self):
            return []

    pipeline = CatalogPipeline(configured(settings), factory, FakeDiscovery([]), llm_service=Unavailable())
    try:
        for attempt in range(1, 4):
            result = pipeline.run(discover=False, only_urls=[article.url], reanalyze=False)
            assert result["counts"]["review_required"] == 1
            with factory() as session:
                row = session.get(Candidate, article.url)
                assert row.article["_llm_retry"]["failures"] == attempt
                assert row.status == "review_required"
                assert row.reason == ("llm_retry_exhausted" if attempt == 3 else "llm_unavailable")
                assert row.status_history
            assert next_candidate(factory, set(), True) != article.url
            skipped = pipeline.run(discover=False, only_urls=[article.url], reanalyze=False)
            assert skipped["counts"]["candidates"] == 0
            with factory.begin() as session:
                row = session.get(Candidate, article.url)
                retry = {**row.article["_llm_retry"], "next_attempt_at": "2000-01-01T00:00:00+00:00"}
                row.article = {**row.article, "_llm_retry": retry}
                row.updated_at = now_utc() - timedelta(days=3)
        assert next_candidate(factory, set(), True) != article.url
    finally:
        pipeline.close()


def test_schema_diagnostics_name_fields_and_types_without_values(settings):
    payload = project_payload(aliases=None, scores={"clarity": "PRIVATE_PAYLOAD"})
    with pytest.raises(ClassifierFailure) as failure:
        parse_classifier_response(payload, "KotibAI works")
    issues = failure.value.schema_issues
    assert {"field": "aliases", "type": "list_type"} in issues
    assert {"field": "scores.clarity", "type": "int_parsing"} in issues
    assert "PRIVATE" not in str(issues)
    with candidate_trace() as trace:
        provider = FakeProvider("groq", [payload])
        service = LLMService(settings.model_copy(update={"llm_provider_order": "groq", "llm_max_retries_per_provider": 0}), providers={"groq": provider})
        with pytest.raises(LLMUnavailable):
            service.analyze_source(sample_article(name="KotibAI"))
    assert trace["provider_attempts"][0]["schema_issues"]
    assert "PRIVATE" not in str(trace)


def test_idle_checkouts_probe_at_most_once_per_120_seconds(monkeypatch):
    from psycopg.pq import TransactionStatus
    ticks = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: ticks[0])
    record = SimpleNamespace(info={})
    connection = Connection(TransactionStatus.IDLE)
    clean_postgres_checkout(connection, record, None)
    for _ in range(10):
        clean_postgres_checkout(connection, record, None)
    assert connection.rollbacks == 1
    ticks[0] += 121
    clean_postgres_checkout(connection, record, None)
    assert connection.rollbacks == 2


def test_source_yield_is_advisory_and_visible_in_admin(settings, factory):
    from backend.app.free_budget import free_status
    with factory.begin() as session:
        session.add_all([RegistrySource(id="news", name="News", url="https://news.example", enabled=True, priority=5),
                         RegistrySource(id="launch", name="Launch", url="https://launch.example", enabled=True, priority=2)])
        session.flush()
        candidates = [{"candidate_id": str(i), "source": {"id": "news", "name": "News", "domain": "news.example"},
                       "stage": "rejected", "reason": "not_a_project"} for i in range(10)]
        session.add(Run(status="completed", started_at=now_utc(), details={"mode": "free_daily", "candidate_runs": candidates}, counts={}))
        for identifier in ("news", "launch"):
            session.add(Candidate(url=f"https://{identifier}.example/item", status="queued", source_id=identifier, article={}))
    with factory() as session:
        report = recent_yield(session)
        assert report[0]["counts"]["evaluated"] == 10
        assert report[0]["deprioritized"]
        assert free_status(session, settings)["source_yield"] == report
        assert session.get(RegistrySource, "news").enabled
    assert next_candidate(factory, set(), True, poor_sources=["news"]) == "https://launch.example/item"


def test_source_yield_ignores_outcomes_caused_by_our_own_limits(settings, factory):
    # Gazeta.uz/namdu.uz regression: LLM outages, budget stops and timeouts are
    # not the source's fault and must not deprioritize it.
    with factory.begin() as session:
        session.add(RegistrySource(id="gazeta", name="Gazeta", url="https://gazeta.example", enabled=True))
        source = {"id": "gazeta", "name": "Gazeta", "domain": "gazeta.example"}
        not_ours = ([{"stage": "review_required", "reason": "llm_unavailable"}] * 8
                    + [{"stage": "review_required", "reason": "llm_retry_exhausted"}] * 2
                    + [{"stage": "budget_stopped", "reason": ""}, {"stage": "timeout", "reason": "candidate_timeout"},
                       {"stage": "worker_failed"}, {"stage": "no_decision", "reason": ""}])
        evaluated = [{"stage": "rejected", "reason": "not_a_project"}] * 9
        session.add(Run(status="completed", started_at=now_utc(), counts={}, details={"mode": "free_daily",
            "candidate_runs": [{"candidate_id": str(i), "source": source, **item}
                               for i, item in enumerate(not_ours + evaluated)]}))
    with factory() as session:
        row = recent_yield(session)[0]
    assert row["counts"]["candidates"] == 23 and row["counts"]["evaluated"] == 9
    assert row["counts"]["llm_unavailable"] == 10
    assert not row["deprioritized"] and row["minimum_basis"] == "evaluated"
    with factory.begin() as session:
        session.add(Run(status="completed", started_at=now_utc(), counts={}, details={"mode": "free_daily",
            "candidate_runs": [{"candidate_id": "x", "source": source, "stage": "fetch_failed", "reason": "http_404"}]}))
    with factory() as session:
        assert recent_yield(session)[0]["deprioritized"]  # A real fetch failure is the source's fault.


def test_selection_rotates_to_the_least_tried_source(factory):
    with factory.begin() as session:
        session.add_all([RegistrySource(id="big", name="Big", url="https://big.example", enabled=True, priority=9),
                         RegistrySource(id="small", name="Small", url="https://small.example", enabled=True, priority=1)])
        session.flush()
        for identifier in ("big", "small"):
            for index in range(2):
                session.add(Candidate(url=f"https://{identifier}.example/{index}", status="queued",
                                      source_id=identifier, article={}))
    assert next_candidate(factory, set(), True).startswith("https://big.example/")
    rotated = next_candidate(factory, set(), True, attempts={"id:big": 1}, with_source=True)
    assert rotated[1] == "small"
    assert next_candidate(factory, set(), True, attempts={"id:big": 1, "id:small": 1}).startswith("https://big.example/")
    assert next_candidate(factory, set(), True, excluded_sources=["id:big"], attempts={"id:big": 3}).startswith(
        "https://small.example/")


@pytest.mark.parametrize("enough_time", [True, False])
def test_gemini_timeout_retries_once_only_when_time_and_budget_allow(settings, factory, monkeypatch, enough_time):
    from backend.app.free_budget import ACTIVE
    from backend.app.llm_service import ProviderFailure
    from tests.test_llm_token_budgets import managed
    budget = managed(settings, factory)
    monkeypatch.setattr(budget, "wait", lambda _: None)
    provider = FakeProvider("gemini", [ProviderFailure("timeout"), {"classification": "NOT_PROJECT", "confidence": .95, "reason": "Market overview"}])
    service = LLMService(settings.model_copy(update={"llm_provider_order": "gemini"}), factory, {"gemini": provider})
    token = ACTIVE.set(budget)
    try:
        with candidate_trace(90 if enough_time else 5) as trace:
            if enough_time:
                assert service.analyze_source(sample_article()).result.classification == "NOT_PROJECT"
                assert provider.calls == budget.used["llm:gemini"] == 2
            else:
                with pytest.raises(LLMUnavailable):
                    service.analyze_source(sample_article())
                assert provider.calls == budget.used["llm:gemini"] == 1
                assert trace["provider_attempts"][0]["retry_skipped"] == "deadline_or_run_budget"
    finally:
        ACTIVE.reset(token)


@pytest.mark.parametrize("db_fixture", ["factory", "postgres_factory"])
def test_publication_writes_are_batched_without_weakening_audit_or_identity(settings, request, db_fixture):
    from backend.app.db import Project, RawDiscovery
    from backend.app.llm_service import LLMAnalysis
    factory = request.getfixturevalue(db_fixture)
    article = sample_article(name="KotibAI")
    with factory.begin() as session:
        session.add(Candidate(url=article.url, status="queued", article=article.model_dump(mode="json")))
    result = parse_classifier_response(project_payload(), article.title + "\n" + article.text)

    class Service:
        available = operational = True
        last_attempt_count = 0
        def analyze_source(self, article):
            return LLMAnalysis(result, "gemini", "offline", 1)
        def status(self):
            return []

    report = run_daily(configured(settings), factory, trial=True, pipeline_factory=lambda config, factory:
                       CatalogPipeline(config, factory, FakeDiscovery([]), llm_service=Service()))
    assert report["counts"]["published"] == 1, report
    writes = report["candidate_runs"][0]["database"]["by_component"]["decision_write"]
    assert writes["sql_queries"] <= 16, writes
    with factory() as session:
        project = session.scalar(select(Project))
        candidate = session.get(Candidate, article.url)
        raw = session.scalar(select(RawDiscovery))
        assert candidate.project_ids == [project.id]
        assert raw.canonical_project_id == project.id
        assert raw.raw_text == article.text
        assert len(project.sources) == len(project.evidence_records) == 1
        assert project.publication_status == "PUBLISHED"


def test_open_provider_circuits_stop_before_spending_candidates(settings, factory):
    article = sample_article()
    with factory.begin() as session:
        session.add(Candidate(url=article.url, status="queued", article=article.model_dump(mode="json")))
    providers = {name: FakeProvider(name, []) for name in ("gemini", "groq")}
    def pipeline(config, factory):
        service = LLMService(config, factory, providers)
        service.failures = {name: config.llm_circuit_breaker_failures for name in providers}
        return CatalogPipeline(config, factory, FakeDiscovery([]), llm_service=service)
    result = run_daily(configured(settings), factory, trial=True, pipeline_factory=pipeline)
    assert result["stop_reason"] == "no_healthy_llm_provider"
    assert result["counts"]["attempted"] == 0
    assert result["usage"].get("candidates", 0) == 0
    with factory() as session:
        assert session.get(Candidate, article.url).status == "queued"
