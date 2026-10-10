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
