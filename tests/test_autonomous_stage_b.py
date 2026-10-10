from sqlalchemy import func, select

from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.catalog_store import save_catalog_result
from backend.app.db import Candidate, Project, RawDiscovery
from backend.app.llm_service import LLMAnalysis, LLMUnavailable
from backend.app.scheduler import make_scheduler
from tests.conftest import FakeDiscovery, sample_article


class InspectingService:
    available = True
    def __init__(self, factory, result):
        self.factory, self.result, self.calls = factory, result, 0
    def analyze_source(self, article):
        with self.factory() as session:
            raw = session.scalar(select(RawDiscovery).where(RawDiscovery.source_url == article.url))
            assert raw and raw.raw_text == article.text and raw.status == "processing"
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return LLMAnalysis(self.result, "gemini", "offline-model", 1)
    def status(self):
        return []


def test_raw_is_committed_before_provider_and_project_publishes_without_deep_score(settings, factory):
    article = sample_article()
    entry = CatalogEntry(name="AgroKo‘mak", confidence=0.9,
                         description_uz="AgroKo‘mak talabalar arizalarini bir joyda qabul qiladi va ko‘rib chiqishni tezlashtiradi.",
                         scores={"clarity": 6, "real_product": 5, "novelty": 4, "potential": 4},
                         score_evidence={"novelty": False, "potential": False},
                         score_reasons={"clarity": "Clear product", "real_product": "Prototype described",
                                        "novelty": "insufficient evidence; neutral fallback",
                                        "potential": "insufficient evidence; neutral fallback"})
    service = InspectingService(factory, CatalogResult("PROJECT", 0.9, (entry,)))
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([article]), llm_service=service)
    result = pipeline.run()
    assert result["counts"]["auto_published"] == 1 and result["counts"]["raw_discoveries"] == 1
    assert service.calls == 1
    with factory() as session:
        project = session.scalar(select(Project))
        raw = session.scalar(select(RawDiscovery))
        assert project.publication_status == "PUBLISHED" and project.opportunity_score is None
        assert raw.status == "processed" and raw.canonical_project_id == project.id
        assert raw.llm_provider == "gemini" and raw.llm_attempt_count == 1
        assert raw.classifier_prompt_version == "catalog_classifier_v1"
    pipeline.close()


def test_all_providers_unavailable_uses_safe_keyless_review(settings, factory):
    article = sample_article()
    service = InspectingService(factory, LLMUnavailable("llm_unavailable"))
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([article]), llm_service=service)
    result = pipeline.run()
    assert result["counts"]["review_required"] == 1
    with factory() as session:
        raw = session.scalar(select(RawDiscovery))
        assert raw.status == "review_required" and raw.failure_reason == "llm_unavailable"
        assert session.scalars(select(Project)).all() == []
    pipeline.close()


def test_existing_attached_source_skips_provider_before_analysis(settings, factory):
    article = sample_article()
    with factory.begin() as session:
        save_catalog_result(session, article, CatalogResult("PROJECT", 0.9, (
            CatalogEntry(name="AgroKo‘mak", confidence=0.9,
                         description_uz="AgroKo‘mak arizalarni bir joyda to‘playdi va talabalar ishini osonlashtiradi."),),
            analysis_method="deterministic"))
        candidate = session.get(Candidate, article.url)
        candidate.status, candidate.processing_version = "queued", 0
    service = InspectingService(factory, AssertionError("provider should not run"))
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([]), llm_service=service)
    result = pipeline.run(discover=False, reanalyze=False)
    assert result["counts"]["duplicates"] == 1 and service.calls == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 1
        raw = session.scalar(select(RawDiscovery))
        assert raw.status == "processed" and raw.failure_reason == "known_project_source"
    pipeline.close()


def test_scheduler_has_independent_discovery_processing_and_reanalysis(settings, factory):
    scheduler = make_scheduler(settings, factory)
    assert {job.id for job in scheduler.get_jobs()} >= {
        "discovery", "raw_processing", "catalog_reanalysis", "reconciliation"}


def test_project_first_source_uses_bounded_processing_budget(settings, factory):
    from backend.app.db import RegistrySource
    news = sample_article(name="NewsItem", url="https://news.example/story")
    project = sample_article(name="RealTool", url="https://projects.example/tool")
    with factory.begin() as session:
        session.add_all([
            RegistrySource(id="news", name="News", url="https://news.example/rss",
                           source_type="news", priority=5),
            RegistrySource(id="project", name="Projects", url="https://projects.example/",
                           source_type="startup_platform", priority=4),
        ])
    class Discovery(FakeDiscovery):
        def discover(self, now, archive=False):
            return [{"url": news.url, "source_id": "news", "title": news.title},
                    {"url": project.url, "source_id": "project", "title": project.title}], [], 2
    config = settings.model_copy(update={"max_candidates": 1})
    pipeline = CatalogPipeline(config, factory, Discovery([news, project]))
    assert pipeline.run(reanalyze=False)["counts"]["candidates"] == 1
    with factory() as session:
        assert session.get(Candidate, project.url).status == "review_required"
        assert session.get(Candidate, news.url).status == "queued"
    pipeline.close()


def test_review_reprocessing_uses_cached_article_without_fetch(settings, factory):
    article = sample_article()
    with factory.begin() as session:
        session.add(Candidate(url=article.url, article=article.model_dump(mode="json"),
                              status="review_required", reason="legacy_review", processing_version=7))
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([]))
    result = pipeline.run(discover=False, reanalyze=False, review_only=True)
    assert result["counts"]["review_required"] == 1
    with factory() as session:
        row = session.get(Candidate, article.url)
        assert row.processing_version == 8 and row.reason == "llm_unavailable"
    pipeline.close()


def test_legacy_event_candidate_does_not_leave_raw_pending(settings, factory):
    from backend.app.raw_discovery import ingest_raw
    article = sample_article()
    with factory.begin() as session:
        raw, _ = ingest_raw(session, source_adapter="event_discovery", source_url=article.url,
                            title=article.title)
        session.add(Candidate(url=article.url, article=article.model_dump(mode="json"),
                              status="event", reason="event_only", processing_version=7))
        raw_id = raw.id
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([]))
    pipeline.run(discover=False, reanalyze=False)
    with factory() as session:
        raw = session.get(RawDiscovery, raw_id)
        assert raw.status == "processed" and raw.failure_reason == "legacy_event"
        assert session.get(Candidate, article.url).status == "event"
    pipeline.close()


def test_fresh_run_recovers_recent_item_rejected_only_by_archive_window(settings, factory):
    article = sample_article(name="Sovereign", url="https://uzhunt.example/p/sovereign")
    with factory.begin() as session:
        session.add(Candidate(url=article.url, article=article.model_dump(mode="json"),
                              status="rejected", reason="outside_archive_window", processing_version=6))
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([]))
    result = pipeline.run(reanalyze=False)
    assert result["counts"]["recovered_window_rejections"] == 1
    with factory() as session:
        row = session.get(Candidate, article.url)
        assert row.status == "review_required" and row.reason == "llm_unavailable"
    pipeline.close()


def test_fresh_run_does_not_requeue_old_archive_window_rejection(settings, factory):
    article = sample_article(name="OldTool", url="https://example.org/old-tool")
    article.published_at = article.published_at.replace(year=2023)
    with factory.begin() as session:
        session.add(Candidate(url=article.url, article=article.model_dump(mode="json"),
                              status="rejected", reason="outside_archive_window", processing_version=6))
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([]))
    result = pipeline.run(reanalyze=False)
    assert result["counts"]["recovered_window_rejections"] == 0
    with factory() as session:
        assert session.get(Candidate, article.url).status == "rejected"
    pipeline.close()
