"""Offline production-path diagnostics; PostgreSQL variant uses only disposable CI DB."""

import json

import httpx
import pytest
from pydantic import SecretStr

from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.collectors.parsers import parse_article
from backend.app.db import Candidate, RegistrySource, Run, now_utc
from backend.app.free_budget import ACTIVE, BudgetStop, free_status
from backend.app.free_daily import next_candidate, run_daily
from backend.app.llm_service import GeminiProvider, GroqProvider, LLMService, LLMUnavailable
from backend.app.network import FetchError, WebClient
from backend.app.telemetry import candidate_trace, span
from tests.conftest import FakeDiscovery, sample_article
from tests.test_daily_postgres import postgres_factory  # noqa: F401
from tests.test_free_daily import make_budget


@pytest.mark.parametrize(
    "method,html",
    [
        (
            "json_ld",
            '<script type="application/ld+json">{"articleBody":"A real product provides teams with structured customer requests and workflow automation."}</script>',
        ),
        (
            "meta_description",
            '<meta property="og:description" content="A real product provides teams with structured customer requests and workflow automation.">',
        ),
        (
            "meta_description",
            '<meta name="description" content="A real product provides teams with structured customer requests and workflow automation.">',
        ),
        (
            "prose_fallback",
            "<div><p>A real product provides teams with structured customer requests and workflow automation.</p></div>",
        ),
    ],
)
def test_missing_configured_selector_uses_real_source_fallback(method, html):
    with candidate_trace() as trace:
        article = parse_article(
            "<html><title>Fixture</title><body>" + html + "</body></html>",
            "https://fixture.example/project",
            options={"body_selector": ".old-selector"},
        )
    assert "structured customer" in article.text
    assert trace["extraction"][0]["method"] == method
    assert trace["extraction"][0]["selector_missing"]
    assert trace["timings_ms"]["extraction"] >= 0


@pytest.mark.parametrize(
    "html,reason",
    [
        ('<body><script src="app.js"></script></body>', "js_shell"),
        ('<body><div class="paywall">Subscribe</div></body>', "paywall_detected"),
        ("<body></body>", "empty_text"),
    ],
)
def test_empty_body_retains_precise_diagnostic(html, reason):
    with candidate_trace() as trace:
        with pytest.raises(FetchError, match="article_body_missing"):
            parse_article(html, "https://fixture.example/project")
    assert trace["extraction"][0]["reason"] == reason


@pytest.mark.parametrize("status", [403, 404, 429])
def test_http_failures_are_not_retried_and_have_safe_metadata(settings, factory, monkeypatch, status):
    monkeypatch.setattr("backend.app.network.public_dns", lambda *args: None)
    calls = []

    def reply(request):
        calls.append(request.url.path)
        return httpx.Response(status, text="secret response not recorded")

    web = WebClient(settings)
    web.client.close()
    web.client = httpx.Client(transport=httpx.MockTransport(reply))
    budget = make_budget(factory)
    token = ACTIVE.set(budget)
    try:
        with candidate_trace() as trace:
            with pytest.raises(FetchError, match=f"http_{status}"):
                web._fetch("https://fixture.example/project?token=private")
        assert len(calls) == 1 and budget.used["pages"] == 1
        assert trace["fetch"][0]["http_status"] == status
        assert "private" not in json.dumps(trace) and "secret" not in json.dumps(trace)
    finally:
        ACTIVE.reset(token)
        web.close()


@pytest.mark.parametrize("fixture_name", ["factory", "postgres_factory"])
@pytest.mark.parametrize("failure", ["article_body_missing", "invalid_json"])
def test_daily_candidate_diagnostics_persist_and_surface_in_admin(
    settings, request, fixture_name, failure, monkeypatch
, offline_daily_preflight):
    factory = request.getfixturevalue(fixture_name)
    article = sample_article()
    with factory.begin() as session:
        session.add(Candidate(url=article.url, status="queued", article={"_queued": True}))
    monkeypatch.setattr("backend.app.llm_service.public_dns", lambda *args: None)

    def pipeline(config, factory):
        class Discovery(FakeDiscovery):
            def article(self, *args):
                if failure == "article_body_missing":
                    return parse_article(
                        '<html><body><script src="app.js"></script></body></html>', article.url
                    )
                return article

        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"finish_reason": "length", "message": {"content": None, "reasoning": "PRIVATE"}}
                        ]
                    },
                )
            )
        )
        providers = {"groq": GroqProvider("test-key", "openai/gpt-oss-20b", client)}
        llm = LLMService(config.model_copy(update={"llm_provider_order": "groq"}), factory, providers)
        return CatalogPipeline(config, factory, Discovery([]), llm_service=llm)

    result = run_daily(
        settings.model_copy(
            update={"free_provider_quotas_confirmed": True, "groq_api_key": SecretStr("test-key")}
        ),
        factory,
        trial=True,
        pipeline_factory=pipeline,
    )
    item = result["candidate_runs"][0]
    assert item["timings_ms"]["total"] >= 0
    assert item["source"]["domain"] == "news.example"
    if failure == "article_body_missing":
        assert item["stage"] == "fetch_failed"
        assert item["error_codes"] == ["article_body_missing"]
        assert result["counts"]["before_llm"] == 1
        assert result["before_llm_reasons"] == {"article_body_missing": 1}
    else:
        assert item["stage"] == "review_required" and item["reason"] == "llm_unavailable"
        attempt = item["provider_attempts"][0]
        assert attempt["outcome"] == "output_truncated" and attempt["http_status"] == 200
        assert attempt["finish_reason"] == "length"
        assert result["counts"]["reached_llm"] == 1
        assert "PRIVATE" not in json.dumps(result)
    with factory() as session:
        stored = session.get(Run, result["run_id"]).details["candidate_runs"]
        assert stored == result["candidate_runs"]
        assert free_status(session, settings)["last_run"]["candidate_runs"] == stored


def test_asset_rejected_without_fetch_or_llm(settings, factory, offline_daily_preflight):
    url = "https://fixture.example/banner.png"
    with factory.begin() as session:
        session.add(Candidate(url=url, status="queued", article={"_queued": True}))
    result = run_daily(
        settings,
        factory,
        trial=True,
        pipeline_factory=lambda config, factory: CatalogPipeline(config, factory, FakeDiscovery([])),
    )
    assert result["counts"]["rejected"] == 1 and result["counts"]["llm_requests"] == 0
    assert result["usage"].get("pages", 0) == 0
    assert result["before_llm_reasons"] == {"non_content_asset": 1}


def test_trial_prioritizes_good_text_and_project_sources_then_penalizes_failures(factory):
    with factory.begin() as session:
        session.add_all(
            [
                RegistrySource(
                    id="cohort",
                    name="Cohort",
                    url="https://cohort.example",
                    source_type="accelerator",
                    priority=5,
                ),
                RegistrySource(
                    id="news", name="News", url="https://news.example", source_type="news", priority=5
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Candidate(
                    url="https://cohort.example/project", source_id="cohort", status="queued", article={}
                ),
                Candidate(
                    url="https://news.example/ready",
                    source_id="news",
                    status="queued",
                    article={"text": "source evidence " * 30},
                ),
            ]
        )
    assert next_candidate(factory, set(), True) == "https://news.example/ready"
    # After the cached item, project-first beats generic news.
    assert next_candidate(factory, {"https://news.example/ready"}, True) == "https://cohort.example/project"
    with factory.begin() as session:
        for i in range(3):
            session.add(
                Candidate(
                    url=f"https://cohort.example/broken{i}",
                    source_id="cohort",
                    status="error",
                    article={},
                    reason="article_body_missing",
                    updated_at=now_utc(),
                )
            )
        session.add(
            Candidate(url="https://news.example/plain", source_id="news", status="queued", article={})
        )
    assert next_candidate(factory, {"https://news.example/ready"}, True) == "https://news.example/plain"


def test_candidate_deadline_does_not_stop_entire_run(factory, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("backend.app.telemetry.monotonic", lambda: clock[0])
    budget = make_budget(factory)
    with candidate_trace(10):
        clock[0] = 21
        with pytest.raises(FetchError, match="candidate_timeout"):
            budget.check_time()
    assert budget.stop_reason == ""
    budget.check_time()


def test_run_deadline_retains_max_run_reason_even_inside_candidate(factory):
    budget = make_budget(factory)
    budget.deadline = budget.timer() - 1
    with candidate_trace():
        with pytest.raises(BudgetStop, match="max_run_seconds"):
            budget.check_time()


def test_timings_are_exclusive_and_do_not_count_pause_twice(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("backend.app.telemetry.monotonic", lambda: clock[0])
    with candidate_trace() as trace:
        with span("page_read"):
            clock[0] += 1
            with span("pauses"):
                clock[0] += 2
            clock[0] += 1
    assert trace["timings_ms"]["page_read"] == 2000
    assert trace["timings_ms"]["pauses"] == 2000
    assert trace["timings_ms"]["total"] == 4000


@pytest.mark.parametrize(
    "payload,outcome",
    [
        ({"choices": [{"message": {"content": None}, "finish_reason": "stop"}]}, "empty_response"),
        ({"choices": [{"message": {"content": "{oops"}, "finish_reason": "stop"}]}, "invalid_json"),
        (
            {"choices": [{"message": {"content": None, "reasoning": "private"}, "finish_reason": "length"}]},
            "output_truncated",
        ),
    ],
)
def test_groq_provider_specific_failure_not_hidden_as_unavailable(monkeypatch, payload, outcome, settings):
    monkeypatch.setattr("backend.app.llm_service.public_dns", lambda *args: None)

    def reply(req):
        body = json.loads(req.content)
        assert body["reasoning_effort"] == "low"
        return httpx.Response(200, json=payload)

    groq = GroqProvider("test", "openai/gpt-oss-20b", httpx.Client(transport=httpx.MockTransport(reply)))
    service = LLMService(
        settings.model_copy(update={"llm_provider_order": "groq", "llm_max_retries_per_provider": 0}),
        providers={"groq": groq},
    )
    with candidate_trace() as trace:
        with pytest.raises(LLMUnavailable):
            service.analyze_json("Rules", "source", lambda x: x)
    attempt = trace["provider_attempts"][0]
    assert attempt["outcome"] == outcome and attempt["http_status"] == 200
    assert "private" not in json.dumps(trace)


def test_gemini_merges_text_parts_and_ignores_reasoning():
    provider = GeminiProvider(
        "test",
        "gemini-3.1-flash-lite",
        httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {
                                "finishReason": "STOP",
                                "content": {
                                    "parts": [
                                        {"thought": True, "text": "private"},
                                        {"text": '{"ok":'},
                                        {"text": "true}"},
                                    ]
                                },
                            }
                        ]
                    },
                )
            )
        ),
    )
    assert provider.complete("Rules", "source", 1) == {"ok": True}


def test_valid_http_json_with_invalid_schema_has_specific_failure(settings, monkeypatch):
    monkeypatch.setattr("backend.app.llm_service.public_dns", lambda *args: None)
    provider = GroqProvider(
        "test",
        "openai/gpt-oss-20b",
        httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": '{"unrelated":true}'}, "finish_reason": "stop"}]
                    },
                )
            )
        ),
    )
    service = LLMService(
        settings.model_copy(update={"llm_provider_order": "groq", "llm_max_retries_per_provider": 0}),
        providers={"groq": provider},
    )

    def validate(payload):
        raise ValueError("PRIVATE source must not appear in diagnostics")

    with candidate_trace() as trace:
        with pytest.raises(LLMUnavailable):
            service.analyze_json("Rules", "source", validate)
    assert trace["provider_attempts"][0]["outcome"] == "schema_validation_failed"
    assert trace["provider_attempts"][0]["http_status"] == 200
    assert "PRIVATE" not in json.dumps(trace)


def test_local_token_guard_reports_reason_without_http(settings, factory):
    from backend.app.llm_budget import policies

    budget = make_budget(factory, provider_policies=policies(settings))

    class NoHTTP:
        def post(self, *args, **kwargs):
            pytest.fail("Oversize system prompt must never call HTTP")

    provider = GroqProvider("test", "openai/gpt-oss-20b", NoHTTP())
    service = LLMService(
        settings.model_copy(update={"llm_provider_order": "groq"}), factory, {"groq": provider}
    )
    token = ACTIVE.set(budget)
    try:
        with candidate_trace() as trace:
            with pytest.raises(LLMUnavailable):
                service.analyze_json("x" * 30000, "source", lambda x: x)
        assert trace["provider_attempts"][0]["outcome"] == "local_budget"
        assert trace["provider_attempts"][0]["reason"] == "prompt_exceeds_token_limit"
        assert not trace["provider_attempts"][0]["request_sent"]
        assert not budget.used.get("llm:groq")
    finally:
        ACTIVE.reset(token)


def test_daily_fetch_connect_read_timeouts_are_separate(settings, monkeypatch):
    from backend.app.free_daily import profile

    config, _, _ = profile(settings, trial=True)
    web = WebClient(config)
    web.client.close()
    timeouts = []

    def reply(req):
        timeouts.append(req.extensions["timeout"])
        return httpx.Response(
            200, text="User-agent: *\nAllow: /" if req.url.path == "/robots.txt" else "body"
        )

    web.client = httpx.Client(transport=httpx.MockTransport(reply))
    monkeypatch.setattr("backend.app.network.public_dns", lambda *args: None)
    monkeypatch.setattr(web, "_pause", lambda _: None)
    try:
        with candidate_trace():
            web.get("https://fixture.example/project")
        assert len(timeouts) == 2
        assert all(t["connect"] <= 3 and t["read"] <= 8 for t in timeouts)
    finally:
        web.close()
