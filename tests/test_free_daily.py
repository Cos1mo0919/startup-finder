"""Offline budgets, interruption recovery, owner decisions and single-writer safety."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_admin import catalog_action
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.catalog_store import save_catalog_result
from backend.app.db import Candidate, Lease, Project, RawDiscovery, RegistrySource, Run, SchedulerCheckpoint, now_utc
from backend.app.free_budget import ACTIVE, BudgetStop, DailyBudget, free_status, state_name
from backend.app.free_daily import profile, run_daily, ingest_links, next_candidate
from backend.app.llm_service import LLMService, ProviderFailure
from backend.app.main import create_app
from backend.app.raw_discovery import cheap_decision, ingest_raw
from backend.app.writer import WriterBusy, current_writer, writer_scope
from tests.conftest import FakeDiscovery, sample_article
from tests.test_autonomous_stage_a import FakeProvider


def make_budget(factory, **kwargs):
    with factory.begin() as session:
        row = Run(started_at=now_utc(), status="running", details={"mode": "free_daily"}, counts={})
        session.add(row)
        session.flush()
        identifier = row.id
    limits = {"pages": (2, 3), "llm:gemini": (3, 3), "llm:groq": (3, 3)}
    return DailyBudget(factory, kwargs.pop("limits", limits), kwargs.pop("target", 20), 2700, identifier,
                       min_interval=0, **kwargs)


def test_crashed_attempts_remain_spent_and_run_and_day_caps_are_independent(factory):
    first = make_budget(factory)
    first.reserve("pages")
    first.reserve("pages")
    with pytest.raises(BudgetStop, match="run_limit:pages"):
        first.reserve("pages")
    second = make_budget(factory)
    second.reserve("pages")
    with pytest.raises(BudgetStop, match="daily_limit:pages"):
        second.reserve("pages")
    with factory() as session:
        state = session.get(SchedulerCheckpoint, state_name(first.day)).cursor
        assert state["usage"]["pages"] == 3
        assert len(state["events"]) == 3


def test_calendar_day_and_deadline_stop_without_consuming_requests(factory):
    clock = [datetime(2026, 10, 13, 18, 59, tzinfo=timezone.utc)]
    budget = make_budget(factory, clock=lambda: clock[0])
    assert budget.day == "2026-10-13"
    clock[0] += timedelta(minutes=2)
    with pytest.raises(BudgetStop, match="calendar_day_changed"):
        budget.reserve("pages")
    ticks = [0]
    other = make_budget(factory, timer=lambda: ticks[0])
    ticks[0] = 2700
    with pytest.raises(BudgetStop, match="max_run_seconds"):
        other.reserve("pages")
    assert not other.used


def test_rate_limit_disables_provider_until_day_end_including_a_new_service(settings, factory):
    budget = make_budget(factory)
    first = FakeProvider("gemini", [ProviderFailure("rate_limited")])
    second = FakeProvider("groq", [{"classification": "NOT_PROJECT", "confidence": 0.95, "reason": "market overview"}] * 2)
    config = settings.model_copy(update={"llm_provider_order": "gemini,groq", "llm_max_retries_per_provider": 2})
    token = ACTIVE.set(budget)
    try:
        assert LLMService(config, factory, {"gemini": first, "groq": second}).analyze_source(sample_article()).provider == "groq"
        new = LLMService(config, factory, {"gemini": first, "groq": second})
        assert new.analyze_source(sample_article()).provider == "groq"
        assert first.calls == 1 and second.calls == 2
        assert budget.blocked("gemini") == "rate_limited"
    finally:
        ACTIVE.reset(token)
    tomorrow = make_budget(factory, clock=lambda: now_utc() + timedelta(days=1))
    assert tomorrow.blocked("gemini") is None


def test_paid_credentials_are_not_passed_even_when_present(settings):
    original = settings.model_copy(update={"ai_api_key": SecretStr("sentinel"), "openai_api_key": SecretStr("sentinel"),
                                           "openrouter_api_key": SecretStr("sentinel"), "search_api_key": SecretStr("sentinel"),
                                           "gemini_api_key": SecretStr("sentinel"), "groq_api_key": SecretStr("sentinel")})
    config, limits, _ = profile(original)
    assert not any(config.model_dump()[key].get_secret_value() for key in
                   ("ai_api_key", "openai_api_key", "openrouter_api_key", "search_api_key", "gemini_api_key", "groq_api_key"))
    assert config.llm_provider_order == "gemini,groq"
    assert limits["search:brave"] == (0, 0)
    assert not config.scheduler_enabled and not config.database_auto_migrate and not config.startup_data_updates_enabled


def test_trial_caps_goal_time_and_calls(settings):
    config, limits, seconds = profile(settings, trial=True)
    assert config.daily_publish_limit == 5 and seconds == 300
    assert limits["pages"] == (40, 40)
    assert limits["llm:gemini"] == (5, 5) and limits["llm:groq"] == (5, 5)
    assert limits["candidates"] == (20, 20)


class PublishingService:
    available = operational = True
    last_attempt_count = 0
    def analyze_source(self, article):
        from backend.app.free_budget import current_budget
        from backend.app.llm_service import LLMAnalysis
        budget = current_budget()
        budget.reserve("llm:gemini")
        with budget.factory() as session:
            raw = session.scalar(select(RawDiscovery).where(RawDiscovery.source_url == article.url))
            assert raw and raw.raw_text  # durable before spending API budget
        name = article.url.rsplit("/", 1)[-1]
        entry = CatalogEntry(name=name, confidence=0.9,
                             description_uz=f"{name} talabalar arizalarini bir joyda qabul qiladi va kundalik ishni tezlashtiradi")
        return LLMAnalysis(CatalogResult("PROJECT", 0.9, (entry,)), "gemini", "offline-fixture", 1)
    def status(self):
        return []


def publishing_pipeline(config, factory):
    return CatalogPipeline(config, factory, discovery=FakeDiscovery([]), llm_service=PublishingService())


def seed_candidates(factory, names):
    with factory.begin() as session:
        for name in names:
            page = sample_article(name=name, url=f"https://fixture.example/{name}")
            session.add(Candidate(url=page.url, article=page.model_dump(mode="json"), status="queued"))


def test_daily_goal_is_shared_across_restarts_and_backlog_is_preserved(settings, factory, monkeypatch):
    monkeypatch.setattr("backend.app.free_budget.sleep", lambda _: None)
    settings = settings.model_copy(update={"daily_project_target": 2})
    seed_candidates(factory, ["AtlasGarden", "NimbusPay", "VectorScan"])
    first = run_daily(settings, factory, pipeline_factory=publishing_pipeline)
    assert first["counts"]["published"] == 2 and first["stop_reason"] == "daily_project_target"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Project).where(Project.publication_status == "PUBLISHED")) == 2
        assert session.scalar(select(func.count()).select_from(Candidate).where(Candidate.status == "queued")) == 1
        assert session.get(Lease, "pipeline").owner == ""
    again = run_daily(settings, factory, pipeline_factory=publishing_pipeline)
    assert again["counts"]["published"] == 0 and not again["usage"]
    assert again["stop_reason"] == "daily_project_target"


def test_request_cap_stops_pipeline_without_rejecting_the_remaining_candidate(settings, factory):
    settings = settings.model_copy(update={"daily_gemini_requests_per_run": 1, "daily_gemini_requests_per_day": 1})
    seed_candidates(factory, ["AtlasGarden", "NimbusPay"])
    result = run_daily(settings, factory, pipeline_factory=publishing_pipeline)
    assert result["stop_reason"] == "run_limit:llm:gemini"
    assert result["counts"]["published"] == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Candidate).where(Candidate.status == "queued")) == 1


@pytest.mark.parametrize("action", ["HIDE", "REJECT"])
def test_admin_decision_survives_repeated_analysis_and_a_different_source(settings, factory, action):
    article = sample_article(name="OwnerTool")
    result = CatalogResult("PROJECT", 0.9, (CatalogEntry(name="OwnerTool", confidence=0.9,
                            description_uz="OwnerTool arizalarni bir joyda saqlaydi va talabalar ishini osonlashtiradi"),))
    with factory.begin() as session:
        save_catalog_result(session, article, result, settings=settings)
        project = session.scalar(select(Project))
        identifier = project.id
        catalog_action(session, identifier, action, "owner decision", settings=settings)
    for suffix in ("", "different", "another"):
        page = article.model_copy(update={"url": article.url + suffix})
        with factory.begin() as session:
            save_catalog_result(session, page, result, settings=settings)
    with factory() as session:
        project = session.get(Project, identifier)
        assert project.publication_method == "admin" and not project.visible
        assert project.publication_status == ("REJECTED" if action == "REJECT" else "REVIEW_REQUIRED")
        assert project.publication_reason == "owner decision"
        assert session.scalar(select(func.count()).select_from(Project)) == 1
    with factory.begin() as session:
        raw, _ = ingest_raw(session, source_adapter="test", source_url=article.url)
        assert cheap_decision(session, raw)[:2] == ("reject", "admin_decision_preserved")


def test_one_writer_blocks_other_workers_and_admin_actions(settings, factory):
    from backend.app.admin_alerts import send_alerts
    with writer_scope(factory) as owner:
        assert current_writer(factory) == owner
        # A second sessionmaker for the same engine also sees the active context.
        # Simulate another process by clearing only the local context variable.
        from backend.app.writer import OWNER
        token = OWNER.set(None)
        try:
            assert run_daily(settings, factory)["status"] == "busy"
            assert send_alerts(settings, factory)["status"] == "busy"
            with pytest.raises(WriterBusy):
                with writer_scope(factory):
                    pass
            safe = settings.model_copy(update={"startup_data_updates_enabled": False, "database_auto_migrate": False})
            with TestClient(create_app(safe)) as client:
                response = client.post('/api/admin/review/action?url=https://fixture.example/no&action=ACCEPT',
                                       headers={"X-Admin-Key": "test-admin-key"})
                assert response.status_code == 409
        finally:
            OWNER.reset(token)
    with factory() as session:
        assert session.get(Lease, "pipeline").owner == ""


def test_admin_daily_usage_warning_and_last24h(settings, factory):
    budget = make_budget(factory, limits={"pages": (10, 10)})
    for _ in range(8):
        budget.reserve("pages")
    with factory() as session:
        result = free_status(session, settings)
        assert result["warnings"] == ["pages"]
        assert result["usage_today"]["pages"] == result["usage_24h"]["pages"] == 8
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/admin/status').status_code == 401
        assert client.get('/api/admin/status', headers={"X-Admin-Key": "test-admin-key"}).json()["free_daily"]["warnings"] == ["pages"]


def test_raw_ingestion_is_idempotent_and_queue_hint_prioritizes_concrete_project(factory):
    with factory.begin() as session:
        source = RegistrySource(id="fixture", name="Fixture", url="https://fixture.example", source_type="startup_platform")
        session.add(source)
    with factory() as session:
        source = session.get(RegistrySource, "fixture")
    links = [{"url": "https://fixture.example/news", "title": "General news"},
             {"url": "https://fixture.example/app", "title": "New startup project"}]
    assert ingest_links(factory, source, links) == 2
    assert ingest_links(factory, source, links) == 0
    assert next_candidate(factory, set(), False).endswith('/app')


def test_multi_page_defers_remaining_projects_without_losing_them_or_calling_llm_again(settings, factory):
    budget = make_budget(factory, target=1)
    page = sample_article(name="AtlasGarden")
    entries = tuple(CatalogEntry(name=name, confidence=0.9,
                    description_uz=f"{name} arizalarni bir joyda saqlaydi va talabalar ishini osonlashtiradi")
                    for name in ["AtlasGarden", "NimbusPay"])
    token = ACTIVE.set(budget)
    try:
        with factory.begin() as session:
            save_catalog_result(session, page, CatalogResult("MULTI", 0.9, entries), settings=settings.model_copy(update={"daily_publish_limit": 1, "daily_uz_limit": 0}))
        with factory() as session:
            candidate = session.get(Candidate, page.url)
            assert candidate.status == "queued" and len(candidate.article["_deferred_catalog_entries"]) == 1
    finally:
        ACTIVE.reset(token)
    # Raising the target explicitly models a later eligible processing cycle;
    # already published slots remain spent. Saved validated entries need no AI.
    class NoCall(PublishingService):
        def analyze_source(self, article):
            raise AssertionError("deferred extraction must not spend AI again")
    def pipeline(config, factory):
        return CatalogPipeline(config, factory, discovery=FakeDiscovery([]), llm_service=NoCall())
    result = run_daily(settings.model_copy(update={"daily_project_target": 2}), factory, pipeline_factory=pipeline)
    assert result["counts"]["published"] == 1 and not result["usage"].get("llm:gemini")
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 2
        assert session.get(Candidate, page.url).status == "published"


def test_database_size_guard_stops_before_any_request(factory):
    budget = make_budget(factory, max_database_bytes=1)
    with pytest.raises(BudgetStop, match="database_size_guard"):
        budget.reserve("pages")
    assert not budget.used


def test_real_web_client_counts_robots_and_blocks_additional_requests(settings, factory, monkeypatch):
    import httpx
    from backend.app.network import WebClient
    monkeypatch.setattr('backend.app.network.public_dns', lambda *args: None)
    calls = []
    def transport(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nAllow: /" if request.url.path == '/robots.txt' else '<html>project</html>',
                              headers={"Content-Type": "text/plain"})
    web = WebClient(settings)
    web.client.close()
    web.client = httpx.Client(transport=httpx.MockTransport(transport))
    monkeypatch.setattr('backend.app.network.time.sleep', lambda _: None)
    budget = make_budget(factory)
    token = ACTIVE.set(budget)
    try:
        assert web.get('https://fixture.example/project')[0] == b'<html>project</html>'
        with pytest.raises(BudgetStop, match='run_limit:pages'):
            web.get('https://fixture.example/another')
        assert len(calls) == budget.used['pages'] == 2
    finally:
        ACTIVE.reset(token)
        web.close()


def test_source_failure_does_not_stop_next_source_and_raw_is_persisted(settings, factory):
    with factory.begin() as session:
        for identifier in ('bad', 'good'):
            session.add(RegistrySource(id=identifier, name=identifier, url=f'https://{identifier}.example/',
                                       enabled=True, collection_method='direct_page'))
    class Discovery(FakeDiscovery):
        def collect(self, source, now, archive):
            if source.id == 'bad':
                raise RuntimeError('simulated parser bug')
            return [{'url':'https://good.example/project', 'title':'A concrete startup project'}]
    def pipeline(config, factory):
        # Generic keyless candidates correctly stay in review, no fake publication.
        return CatalogPipeline(config, factory, discovery=Discovery([sample_article(url='https://good.example/project')]))
    result = run_daily(settings, factory, pipeline_factory=pipeline)
    assert result['status'] == 'completed'
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RawDiscovery)) >= 1
        assert session.get(RegistrySource, 'bad').consecutive_errors == 1
        assert session.get(RegistrySource, 'good').last_success_at is not None


def test_github_keeps_earlier_results_when_next_query_hits_the_budget(settings, factory, monkeypatch):
    import httpx
    from backend.app.collectors.sources import Discovery
    monkeypatch.setattr('backend.app.network.public_dns', lambda *args: None)
    calls = []
    def response(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={'items':[{'html_url':'https://github.com/fixture/product',
                                                   'description':'An actual fixture product', 'full_name':'fixture/product'}]})
    client = httpx.Client(transport=httpx.MockTransport(response))
    monkeypatch.setattr(httpx,'Client',lambda *args, **kwargs:client)
    budget = make_budget(factory, limits={'search:github':(1,1),'pages':(5,5)})
    discovery = Discovery(settings, SimpleNamespace(proxy_hosts=set()), factory=factory)
    source = SimpleNamespace(options={'queries':['first','second']})
    token = ACTIVE.set(budget)
    try:
        result = discovery.github_search(source)
        assert len(calls) == 1 and result[0]['url'] == 'https://github.com/fixture/product'
        assert budget.stop_reason == 'run_limit:search:github'
    finally:
        ACTIVE.reset(token)
        client.close()
