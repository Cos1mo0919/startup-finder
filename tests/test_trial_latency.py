"""Real code paths with disposable DBs and offline providers; no production URLs."""

from time import monotonic
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select, text

from backend.app.catalog import PROMPT_PATH, parse_classifier_response
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.connection_pool import clean_postgres_checkout
from backend.app.db import Candidate, Project, Run
from backend.app.free_budget import ACTIVE, current_budget
from backend.app.free_daily import profile, run_daily
from backend.app.llm_service import LLMAnalysis, LLMService, LLMUnavailable
from backend.app.network import CandidateTimeout
from backend.app.telemetry import ACTIVE_TRACE, candidate_trace, db_work
from tests.conftest import FakeDiscovery, sample_article
from tests.test_autonomous_stage_a import FakeProvider
from tests.test_catalog_v31 import project_payload
from tests.test_connection_hygiene import Connection
from tests.test_daily_postgres import postgres_factory  # noqa:F401
from tests.test_llm_token_budgets import managed


def config(settings):
    return settings.model_copy(
        update={
            "free_provider_quotas_confirmed": True,
            "gemini_api_key": SecretStr("offline"),
            "daily_llm_min_interval_seconds": 0,
        }
    )


def seed(factory):
    article = sample_article(name="KotibAI")
    with factory.begin() as session:
        session.add(Candidate(url=article.url, status="queued", article=article.model_dump(mode="json")))
    return article


def test_database_queries_transactions_and_components_are_measured(factory):
    with candidate_trace() as trace:
        with db_work("quota_before_http"):
            with factory.begin() as session:
                session.execute(text("SELECT 1"))
        with factory() as session:
            session.execute(text("SELECT 2"))
    stats = trace["database"]
    assert stats["sql_queries"] == 2
    assert stats["commits"] >= 1 and stats["rollbacks"] >= 1
    assert stats["by_component"]["quota_before_http"]["sql_queries"] == 1
    assert stats["elapsed_ms"] >= 0 and trace["timings_ms"]["db_sql"] >= 0
    assert "SELECT" not in str(trace)


def test_rule_code_is_precise_and_does_not_include_response(settings):
    payload = project_payload(scores={"clarity": 7, "real_product": 9, "novelty": 4, "potential": 4})
    provider = FakeProvider("gemini", [payload])
    service = LLMService(
        settings.model_copy(update={"llm_provider_order": "gemini", "llm_max_retries_per_provider": 0}),
        providers={"gemini": provider},
    )
    with candidate_trace() as trace:
        with pytest.raises(LLMUnavailable):
            service.analyze_json(
                "Rules", "private source", lambda data: parse_classifier_response(data, "KotibAI works")
            )
    item = trace["provider_attempts"][0]
    assert item["outcome"] == "business_validation_failed"
    assert item["rule_code"] == "real_product_usage_unsupported"
    assert "private source" not in str(trace)
    assert trace["timings_ms"]["validation"] >= 0


@pytest.mark.parametrize("db_fixture", ["factory", "postgres_factory"])
@pytest.mark.parametrize("expire_global", [False, True])
def test_validated_response_survives_deadline_and_resumes_without_llm(
    settings, request, db_fixture, expire_global
):
    factory = request.getfixturevalue(db_fixture)
    article = seed(factory)
    result = parse_classifier_response(project_payload(), article.title + "\n" + article.text)
    calls = []

    class Service:
        available = operational = True
        last_attempt_count = 0

        def analyze_source(self, article):
            calls.append(1)
            if len(calls) > 1:
                pytest.fail("Validated continuation must not call provider twice")
            if expire_global:
                current_budget().deadline = current_budget().timer() - 1
            else:
                ACTIVE_TRACE.get()["deadline"] = monotonic() - 1
            return LLMAnalysis(result, "gemini", "fixture-model", 1)

        def status(self):
            return []

    def pipeline(settings, factory):
        return CatalogPipeline(settings, factory, FakeDiscovery([]), llm_service=Service())

    first = run_daily(config(settings), factory, trial=True, pipeline_factory=pipeline)
    if expire_global:
        assert first["stop_reason"] == "max_run_seconds"
        with factory() as session:
            assert (
                session.get(Candidate, article.url).article["_validated_catalog_result"]["name"] == "KotibAI"
            )
        second = run_daily(config(settings), factory, trial=True, pipeline_factory=pipeline)
        assert second["counts"]["published"] == 1, second
    else:
        assert first["counts"]["published"] == 1, first
        assert first["counts"]["timeouts"] == 0
    with factory() as session:
        assert session.scalar(select(Project)).publication_status == "PUBLISHED"
    assert len(calls) == 1


def test_candidate_timeout_is_not_fetch_failure(settings, factory):
    article = seed(factory)
    with factory.begin() as session:
        row = session.get(Candidate, article.url)
        row.article = {"_queued": True}

    class Discovery(FakeDiscovery):
        def article(self, *args):
            raise CandidateTimeout("candidate_timeout")

    result = run_daily(
        config(settings),
        factory,
        trial=True,
        pipeline_factory=lambda settings, factory: CatalogPipeline(settings, factory, Discovery([])),
    )
    assert result["counts"]["timeouts"] == 1 and result["counts"]["fetch_failed"] == 0
    assert result["candidate_runs"][0]["stage"] == "timeout"


def test_two_compact_groq_requests_fit_minute_reserve_without_wait(settings, factory):
    budget = managed(settings, factory)
    waits = []
    budget.wait = lambda seconds: waits.append(seconds)
    provider = FakeProvider("groq", [{"ok": True}, {"ok": True}])
    service = LLMService(
        settings.model_copy(update={"llm_provider_order": "groq"}), factory, {"groq": provider}
    )
    token = ACTIVE.set(budget)
    try:
        with candidate_trace() as trace:
            for _ in range(2):
                service.analyze_json(
                    PROMPT_PATH.read_text(),
                    "long source " * 1000,
                    lambda x: x,
                    compact_system=(PROMPT_PATH.parent / "catalog_classifier_compact_v3.txt").read_text(),
                )
        reserves = [item["estimated_total"] for item in trace["token_reservations"]]
        assert len(reserves) == 2 and sum(reserves) <= 8000
        assert all(value <= 3872 for value in reserves)
        assert waits == []
    finally:
        ACTIVE.reset(token)


def test_trial_default_300_explicit_maximum_600(settings):
    assert profile(settings, True)[2] == 300
    assert profile(settings.model_copy(update={"trial_max_run_seconds": 600}), True)[2] == 600
    with pytest.raises(ValidationError):
        type(settings)(database_url=settings.database_url, trial_max_run_seconds=601)


def test_run_phases_and_sql_counts_persist_for_admin(settings, factory):
    result = run_daily(settings, factory, trial=True)
    assert result["run_database"]["sql_queries"] > 0
    assert result["run_phases_ms"]["initialization"] >= 0
    with factory() as session:
        row = session.get(Run, result["run_id"])
        assert row.details["run_phases_ms"]["initialization"] >= 0
        assert row.details["run_database"]["sql_queries"] > 0


def test_checkout_skips_repeat_probe_but_always_discards_active_socket():
    from psycopg.pq import TransactionStatus
    from sqlalchemy import exc

    record = SimpleNamespace(info={})
    connection = Connection(TransactionStatus.IDLE)
    clean_postgres_checkout(connection, record, None)
    rollbacks = connection.rollbacks
    clean_postgres_checkout(connection, record, None)
    assert connection.rollbacks == rollbacks
    connection.info.transaction_status = TransactionStatus.ACTIVE
    with pytest.raises(exc.DisconnectionError):
        clean_postgres_checkout(connection, record, None)


def test_committed_ledger_precedes_http_and_actual_usage_is_reconciled(settings, factory, monkeypatch):
    import httpx
    from backend.app.llm_service import GroqProvider
    from backend.app.llm_budget import quota_status

    monkeypatch.setattr("backend.app.llm_service.public_dns", lambda *args: None)
    budget = managed(settings, factory)

    def reply(request):
        # Independent session sees committed reservation before the mock network receives HTTP.
        with factory() as session:
            quota = quota_status(session, budget.clock())["groq"]
            assert quota["requests"] == 1 and quota["tokens"] > 0
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"classification":"NOT_PROJECT","confidence":0.9,"reason":"fixture noise"}'
                        },
                    }
                ],
                "usage": {"total_tokens": 500},
            },
        )

    service = LLMService(
        settings.model_copy(update={"llm_provider_order": "groq"}),
        factory,
        {
            "groq": GroqProvider(
                "offline", "openai/gpt-oss-20b", httpx.Client(transport=httpx.MockTransport(reply))
            )
        },
    )
    token = ACTIVE.set(budget)
    try:
        with candidate_trace() as trace:
            result = service.analyze_source(sample_article())
        assert result.result.classification == "NOT_PROJECT"
        with factory() as session:
            assert quota_status(session, budget.clock())["groq"]["reported_tokens"] == 500
        assert trace["database"]["by_component"]["quota_before_http"]["sql_queries"] > 0
        assert trace["database"]["by_component"]["quota_after_http"]["sql_queries"] > 0
    finally:
        ACTIVE.reset(token)


def test_minute_token_wait_is_pauses_not_other(settings, factory, monkeypatch):
    from datetime import timedelta

    budget = managed(settings, factory)
    start = budget.clock()
    clock = [0.0]
    budget.clock = lambda: start + timedelta(seconds=clock[0])
    monkeypatch.setattr("backend.app.telemetry.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "backend.app.free_budget.sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    budget.quotas.reserve("groq", 5500)
    clock[0] = 40
    with candidate_trace() as trace:
        budget.quotas.reserve("groq", 5500)
    assert trace["timings_ms"]["pauses"] >= 20000
    assert trace["provider_waits"][0]["reason"] == "tpm_reserved_tokens"
    assert not trace["provider_waits"][0]["skipped"]
    assert trace["timings_ms"]["other"] < 1


@pytest.mark.parametrize(
    "result,expected",
    [
        (
            {
                "status": "completed",
                "counts": {"llm_validated": 5, "processed": 5, "published": 0, "timeouts": 0},
            },
            "passed",
        ),
        ({"status": "completed", "counts": {"attempted": 5, "llm_validated": 5, "processed": 4}}, "partial"),
        ({"status": "failed", "counts": {"worker_failed": 1}}, "failed"),
        ({"status": "completed", "counts": {"attempted": 0}}, "not_started"),
    ],
)
def test_trial_evaluation_requires_completed_decisions_not_publication_quota(result, expected):
    from backend.app.free_daily import trial_evaluation

    assert trial_evaluation(result) == expected


@pytest.mark.parametrize("db_fixture", ["factory", "postgres_factory"])
def test_publication_failures_back_off_then_require_review_without_repeated_llm(settings, request, db_fixture):
    from sqlalchemy import event, func
    from backend.app.db import Lease, now_utc
    from backend.app.free_daily import next_candidate
    from backend.app.publication_retry import MAX_FAILURES

    factory = request.getfixturevalue(db_fixture)
    article = seed(factory)
    result = parse_classifier_response(project_payload(), article.title + "\n" + article.text)
    calls = []

    class Service:
        available = operational = True
        last_attempt_count = 0

        def analyze_source(self, article):
            calls.append(1)
            assert len(calls) == 1, "Retry must reuse validated checkpoint"
            return LLMAnalysis(result, "gemini", "fixture-model", 1)

        def status(self):
            return []

    def pipeline(settings, factory):
        return CatalogPipeline(settings, factory, FakeDiscovery([]), llm_service=Service())

    def fail_publication(session, context):
        if any(isinstance(row, Project) for row in session.identity_map.values()):
            raise RuntimeError("Offline publication failure")

    event.listen(factory, "after_flush_postexec", fail_publication)
    try:
        for attempt in range(1, MAX_FAILURES + 1):
            failed = run_daily(config(settings), factory, trial=True, pipeline_factory=pipeline)
            assert failed["status"] == "failed"
            with factory() as session:
                row = session.get(Candidate, article.url)
                retry = row.article["_publication_retry"]
                assert retry["failures"] == attempt
                assert row.article["_validated_catalog_result"]["classification"] == "PROJECT"
                assert session.scalar(select(func.count()).select_from(Project)) == 0
                assert session.get(Lease, "pipeline").owner == ""
                assert len([x for x in row.status_history if x["analysis_method"] == "publication_retry"]) == attempt
                if attempt == MAX_FAILURES:
                    assert row.status == "review_required"
                    assert row.reason == "publication_retry_exhausted"
                else:
                    from datetime import datetime
                    assert datetime.fromisoformat(retry["next_attempt_at"]) > now_utc()
            assert next_candidate(factory, set(), True) is None
            skipped = run_daily(config(settings), factory, trial=True, pipeline_factory=pipeline)
            assert skipped["counts"]["attempted"] == 0
            assert skipped["usage"].get("candidates", 0) == 0
            # Explicit processing also respects retry eligibility, not just daily selection.
            direct = pipeline(config(settings), factory).run(discover=False, only_urls=[article.url], reanalyze=False)
            assert direct["counts"]["auto_published"] == 0
            if attempt < MAX_FAILURES:
                with factory.begin() as session:
                    row = session.get(Candidate, article.url)
                    retry = {**row.article["_publication_retry"], "next_attempt_at": "2000-01-01T00:00:00+00:00"}
                    row.article = {**row.article, "_publication_retry": retry}
        assert calls == [1]
    finally:
        event.remove(factory, "after_flush_postexec", fail_publication)
