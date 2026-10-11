import json
from datetime import date
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_store import save_catalog_result
from backend.app.catalog_admin import catalog_action
from backend.app.collectors.sources import structured_project_fields
from backend.app.db import Candidate, Project, Run
from tests.conftest import FakeDiscovery, sample_article


def test_keyless_news_is_review_not_published(settings, factory):
    page = sample_article()
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([page]))
    result = pipeline.run()
    assert result["counts"]["auto_published"] == 0
    assert result["counts"]["review_required"] == 1
    assert result["details"]["limits"]["archive_pages"] == settings.archive_pages
    assert "coverage" in result["details"] and "remaining_queue" in result["details"]
    with factory() as session:
        candidate = session.get(Candidate, page.url)
        assert candidate.reason == "llm_unavailable"
        assert session.scalars(select(Project)).all() == []
    # A second drain does not revisit an unchanged keyless review record.
    assert pipeline.run(discover=False)["counts"]["candidates"] == 0
    pipeline.close()


def test_large_global_queue_does_not_starve_local_source(settings, factory):
    from backend.app.db import RegistrySource

    global_pages = [sample_article(name=f"Global{i}", url=f"https://global.example/tool-{i}")
                    for i in range(3)]
    local = sample_article(name="LocalTool", url="https://local.example/tool")
    with factory.begin() as session:
        session.add_all([
            RegistrySource(id="show-hn-rss", name="Global", url="https://hnrss.org/show",
                           source_type="community", priority=2),
            RegistrySource(id="local", name="Local", url="https://local.example/",
                           source_type="startup_platform", priority=5),
        ])

    class Discovery(FakeDiscovery):
        def discover(self, now, archive=False):
            return ([{"url": page.url, "source_id": "show-hn-rss"} for page in global_pages] +
                    [{"url": local.url, "source_id": "local"}]), [], 2

    pipeline = CatalogPipeline(settings.model_copy(update={"max_candidates": 2}), factory,
                               Discovery([*global_pages, local]))
    pipeline.run(reanalyze=False)
    with factory() as session:
        assert session.get(Candidate, local.url).status == "review_required"
        assert sum(session.get(Candidate, page.url).status == "review_required"
                   for page in global_pages) == 1
    pipeline.close()


def test_show_hn_page_with_only_short_listing_stays_in_review(settings, factory):
    page = sample_article(name="Reclip", url="https://example.org/listing")
    page.source_id = "show-hn-rss"
    page.title = "Video prompts | Reclip"
    page.text = "One short video prompt and a link to another page."
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([page]))
    result = pipeline.run(reanalyze=False)
    assert result["counts"]["auto_published"] == 0
    with factory() as session:
        candidate = session.get(Candidate, page.url)
        assert candidate.status == "review_required"
        assert candidate.reason == "source_excerpt_insufficient"
    pipeline.close()


def test_large_archive_ingestion_commits_idempotent_chunks(settings, factory):
    articles = [sample_article(name=f"Tool{i}", url=f"https://news.example/tool-{i}")
                for i in range(255)]
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery(articles))
    first = pipeline.run(archive=True, process=False, reanalyze=False)
    assert first["counts"]["raw_discoveries"] == 255
    second = pipeline.run(archive=True, process=False, reanalyze=False)
    assert second["counts"]["raw_discoveries"] == 0
    with factory() as session:
        assert len(session.scalars(select(Candidate)).all()) == 255
    pipeline.close()


def test_source_match_to_hidden_project_is_not_a_published_duplicate(settings, factory):
    from backend.app.raw_discovery import cheap_decision, ingest_raw

    page = sample_article()
    entry = CatalogEntry(name="AgroKo‘mak", confidence=0.9,
                         description_uz="AgroKo‘mak fermerlarga suv sarfini kuzatish va sug‘orishni rejalash imkonini beradi")
    with factory.begin() as session:
        save_catalog_result(session, page, CatalogResult("PROJECT", 0.9, (entry,)))
        project = session.scalar(select(Project))
        project.publication_status = "REVIEW_REQUIRED"
        raw, _ = ingest_raw(session, source_adapter="test", source_url=page.url, title=page.title)
        assert cheap_decision(session, raw)[0] == "classify"


def test_keyless_scholarship_is_rejected(settings, factory):
    page = sample_article()
    page.title = "Davlat stipendiyasi uchun arizalar boshlandi"
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([page]))
    assert pipeline.run()["counts"]["rejected"] == 1
    with factory() as session:
        assert session.get(Candidate, page.url).status == "rejected"
    pipeline.close()


def test_explicit_trusted_pair_auto_publishes_and_is_idempotent(settings, factory, tmp_path):
    allowlist = tmp_path / "trusted.json"
    allowlist.write_text(json.dumps({"entries": [{"adapter": "official-demo", "page_type": "startup_profile",
                                                "trusted_for_deterministic_publish": True}]}))
    settings = settings.model_copy(update={"trusted_catalog_file": allowlist})
    page = sample_article("AgroKo‘mak")
    page.adapter, page.page_type = "official-demo", "startup_profile"
    page.project_name = "AgroKo‘mak"
    page.project_description = "AgroKo‘mak fermerlarga dala holatini kuzatish, sug‘orishni rejalash va hosil ma’lumotlarini bir joyda boshqarish imkonini beradi."
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([page]))
    first = pipeline.run()
    assert first["counts"]["auto_published"] == 1
    assert pipeline.run(discover=False)["counts"]["auto_published"] == 0
    with factory() as session:
        project = session.scalar(select(Project))
        assert project.publication_status == "PUBLISHED"
        assert project.catalog_score is None and project.score_pending
        assert project.evidence_count == 0
        assert project.analysis_method == "deterministic"
        assert project.publication_excerpt in page.text
        assert len(session.scalars(select(Project)).all()) == 1
    pipeline.close()


def test_source_failure_is_isolated(settings, factory):
    page = sample_article()
    class Discovery(FakeDiscovery):
        def discover(self, now, archive=False):
            return [{"url": page.url}], [{"source": "broken", "stage": "source", "code": "http_503"}], 2
    pipeline = CatalogPipeline(settings, factory, Discovery([page]))
    result = pipeline.run()
    assert result["status"] == "partial"
    assert result["counts"]["review_required"] == 1
    with factory() as session:
        assert session.scalar(select(Run).order_by(Run.id.desc())).errors[0]["code"] == "http_503"
    pipeline.close()


def test_only_source_does_not_run_unrelated_event_followups(settings, factory):
    page = sample_article()
    class Discovery(FakeDiscovery):
        def follow_events(self, now):
            raise AssertionError("Event follow-ups must respect --only-source")
    pipeline = CatalogPipeline(settings, factory, Discovery([page]))
    result = pipeline.run(only_source="spot", force_sources=True)
    assert result["counts"]["new_candidates"] == 1
    pipeline.close()


def test_discovery_origin_survives_queue_and_differs_from_project_page(settings, factory, tmp_path):
    allowlist = tmp_path / "trusted.json"
    allowlist.write_text(json.dumps({"entries": [{"adapter": "official-demo", "page_type": "startup_profile",
                                               "trusted_for_deterministic_publish": True}]}))
    settings = settings.model_copy(update={"trusted_catalog_file": allowlist})
    page = sample_article()
    page.adapter, page.page_type = "official-demo", "startup_profile"
    page.project_name = "AgroKo‘mak"
    page.project_description = "AgroKo‘mak fermerlarga dala holatini kuzatish, sug‘orishni rejalash va hosil ma’lumotlarini bir joyda boshqarish imkonini beradi."
    class Discovery(FakeDiscovery):
        def discover(self, now, archive=False):
            return [{"url": page.url, "discovery_url": "https://news.ycombinator.com/item?id=123",
                     "title": "Show HN: AgroKo‘mak"}], [], 1
    pipeline = CatalogPipeline(settings, factory, Discovery([page]))
    assert pipeline.run()["counts"]["auto_published"] == 1
    with factory() as session:
        project = session.scalar(select(Project))
        assert project.discovery_source_url == "https://news.ycombinator.com/item?id=123"
        assert project.sources[0].url == page.url
    pipeline.close()


def test_structured_adapter_extracts_explicit_fields_only():
    html = b'<h1>Demo</h1><p class="summary">Farmers schedule irrigation with field measurements and avoid wasted water.</p>'
    assert structured_project_fields(html, {"project_name_selector": "h1", "project_description_selector": ".summary"}) == (
        "Demo", "Farmers schedule irrigation with field measurements and avoid wasted water.")
    assert structured_project_fields(b'<h1>Generic news</h1>', {}) == ("", "")


def test_backfill_rejects_page_outside_requested_year(settings, factory):
    page = sample_article()
    discovery = FakeDiscovery([page])
    discovery.window = (date(2022, 1, 1), date(2022, 12, 31))
    pipeline = CatalogPipeline(settings, factory, discovery)
    result = pipeline.run(archive=True)
    assert result["counts"]["rejected"] == 1
    with factory() as session:
        candidate = session.get(Candidate, page.url)
        assert candidate.reason == "outside_archive_window"
        assert session.scalars(select(Project)).all() == []
    pipeline.close()


def test_llm_key_reprocesses_review_and_publishes(settings, factory):
    page = sample_article()
    discovery = FakeDiscovery([page])
    keyless = CatalogPipeline(settings, factory, discovery)
    assert keyless.run()["counts"]["review_required"] == 1
    keyless.close()

    class Classifier:
        def classify(self, article):
            return CatalogResult("PROJECT", 0.91, (
                CatalogEntry(name="AgroKo‘mak", description_uz="Talabalar arizalarini bir joyda qabul qiladi va ko‘rib chiqish jarayonini tezlashtiradi.",
                             confidence=0.91, scores={"clarity": 7, "real_product": 6, "novelty": 4, "potential": 4},
                             score_evidence={"novelty": False, "potential": False},
                             score_reasons={"clarity": "aniq", "real_product": "mavjud", "novelty": "insufficient evidence; neutral fallback", "potential": "insufficient evidence; neutral fallback"}),
            ))
    keyed = settings.model_copy(update={"ai_api_key": SecretStr("test"), "reanalysis_delay_seconds": 0})
    pipeline = CatalogPipeline(keyed, factory, discovery, classifier=Classifier())
    assert pipeline.run(discover=False)["counts"]["auto_published"] == 1
    with factory() as session:
        project = session.scalar(select(Project))
        assert project.publication_status == "PUBLISHED"
        assert project.analysis_method == "llm"
        assert session.get(Candidate, page.url).status == "published"
    pipeline.close()


def test_admin_hide_publish_and_merge_preserves_sources(settings, factory):
    first = sample_article("AgroKo‘mak", "https://news.example/first")
    second = sample_article("Boshqa mahsulot", "https://news.example/second")
    def result(name):
        return CatalogResult("PROJECT", 0.9, (CatalogEntry(name=name, confidence=0.9,
            description_uz="Mahsulot fermerlar uchun sug‘orish va hosil yozuvlarini bir joyda boshqarish imkonini beradi.",
            scores={"clarity": 6, "real_product": 6, "novelty": 4, "potential": 4},
            score_evidence={"novelty": False, "potential": False},
            score_reasons={"clarity": "aniq", "real_product": "mavjud", "novelty": "insufficient evidence; neutral fallback", "potential": "insufficient evidence; neutral fallback"}),))
    with factory.begin() as session:
        save_catalog_result(session, first, result("AgroKo‘mak"))
        save_catalog_result(session, second, result("Boshqa mahsulot"))
    with factory.begin() as session:
        projects = list(session.scalars(select(Project).order_by(Project.name)))
        target, source = projects
        catalog_action(session, source.id, "HIDE", "needs_review")
        assert source.publication_status == "REVIEW_REQUIRED"
        catalog_action(session, source.id, "PUBLISH", "admin_checked")
        catalog_action(session, source.id, "MERGE", "same_entity", target.id)
    with factory() as session:
        target = session.get(Project, target.id)
        assert {row.url for row in target.sources} == {first.url, second.url}
        assert session.get(Project, source.id).publication_status == "DUPLICATE"
