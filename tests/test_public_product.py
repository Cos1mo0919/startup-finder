from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.collectors.parsers import parse_feed
from backend.app.collectors.sources import Discovery
from backend.app.db import Candidate, Project, EcosystemSignal, RegistrySource, now_utc
from backend.app.detection import project_detector
from backend.app.analysis import ExtractiveAnalyzer
from backend.app.main import create_app
from backend.app.pipeline import Pipeline
from tests.conftest import FakeAnalyzer, FakeDiscovery, sample_article


def test_detector_ignores_unrelated_notices_and_keeps_market_signal():
    for title in (
        "Polshada magistratura stipendiyasi uchun arizalar",
        "O‘qituvchilar uchun yangi soliq tartibi",
        "Universitetga qabul imtihonlari boshlandi",
    ):
        article = sample_article()
        article.title = title
        assert project_detector(article)[0] == "NON_PROJECT"
    article = sample_article()
    article.title = "Yangi startup fondi investitsiya ajratadi"
    article.text = "O‘zbekistonda venchur fond startaplarni moliyalashtiradi."
    assert project_detector(article)[0] == "SIGNAL_ONLY"


def test_verified_but_incomplete_project_is_admin_only(settings, factory):
    article = sample_article("AquaSense")
    article.text = "O‘zbekiston uchun AquaSense platformasi Ali Karimov tomonidan ishlab chiqildi. Fermerlar uchun prototip taqdim etildi."
    result = Pipeline(settings, factory, FakeDiscovery([article])).run()
    assert result["counts"]["new_projects"] == 0
    with factory() as session:
        project = session.scalar(select(Project))
        candidate = session.get(Candidate, article.url)
        assert project.publication_status == "REVIEW_REQUIRED"
        assert candidate.status == "review_required"
        assert candidate.reason == project.publication_reason
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects?period=all").json()["total"] == 0
        assert client.get(f"/api/projects/{project.id}").status_code == 404
        assert client.get("/api/admin/review").status_code == 401
        queue = client.get("/api/admin/review", headers={"X-Admin-Key": "test-admin-key"}).json()
        assert queue["total"] == 1
        assert queue["items"][0]["reason"] == project.publication_reason


def test_admin_accept_requeues_without_bypassing_publication(settings, factory):
    article = sample_article("AquaSense")
    article.text = "O‘zbekiston uchun AquaSense platformasi Ali Karimov tomonidan ishlab chiqildi. Fermerlar uchun prototip taqdim etildi."
    Pipeline(settings, factory, FakeDiscovery([article])).run()
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/admin/review/action", params={"url": article.url, "action": "ACCEPT"}, headers={"X-Admin-Key": "test-admin-key"})
        assert response.status_code == 200
        assert client.get("/api/projects?period=all").json()["total"] == 0
    with factory() as session:
        assert session.get(Candidate, article.url).status == "queued"


def test_admin_reject_requires_and_stores_reason(settings, factory):
    article = sample_article("AquaSense")
    article.text = "O‘zbekiston uchun AquaSense platformasi Ali Karimov tomonidan ishlab chiqildi. Fermerlar uchun prototip taqdim etildi."
    Pipeline(settings, factory, FakeDiscovery([article])).run()
    with TestClient(create_app(settings)) as client:
        headers = {"X-Admin-Key": "test-admin-key"}
        assert client.post("/api/admin/review/action", params={"url": article.url, "action": "REJECT"}, headers=headers).status_code == 422
        response = client.post("/api/admin/review/action", params={"url": article.url, "action": "REJECT", "reason": "insufficient_evidence"}, headers=headers)
        assert response.status_code == 200
    with factory() as session:
        candidate = session.get(Candidate, article.url)
        assert (candidate.status, candidate.reason, candidate.review_decision) == ("rejected", "insufficient_evidence", "REJECT")


def test_legacy_published_label_is_reconciled_with_public_gate(settings, factory):
    article = sample_article("AquaSense")
    article.text = "O‘zbekiston uchun AquaSense platformasi Ali Karimov tomonidan ishlab chiqildi. Fermerlar uchun prototip taqdim etildi."
    Pipeline(settings, factory, FakeDiscovery([article])).run()
    with factory.begin() as session:
        candidate = session.get(Candidate, article.url)
        candidate.status, candidate.reason, candidate.project_ids = "published", "", []
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/admin/status", headers={"X-Admin-Key": "test-admin-key"}).json()
        assert status["total_projects"] == status["publication_counts"]["published_projects"] == 0
        assert status["processing_summary"]["review_required"] == 1
        assert client.get("/api/projects?period=all").json()["total"] == 0
    with factory() as session:
        candidate = session.get(Candidate, article.url)
        assert candidate.status == "review_required" and candidate.project_ids


def test_historical_publication_date_does_not_make_project_new(settings, factory):
    article = sample_article()
    article.published_at = datetime(2022, 4, 11, tzinfo=timezone.utc)
    Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run(archive=True)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects?period=today").json()["total"] == 0
        assert client.get("/api/projects?year=2022").json()["total"] == 1
        assert client.get("/api/intelligence/dashboard").json()["today"]["projects"] == 0


def test_show_hn_feed_preserves_primary_and_discovery_urls():
    raw = b'<rss><channel><item><title>Show HN: Example product</title><link>https://example.org/product</link><comments>https://news.ycombinator.com/item?id=123</comments><pubDate>Fri, 09 Oct 2026 06:57:45 +0000</pubDate></item></channel></rss>'
    item = parse_feed(raw)[0]
    assert item["url"] == "https://example.org/product"
    assert item["discovery_url"] == "https://news.ycombinator.com/item?id=123"


def test_show_hn_collects_product_links_not_generic_items(settings, factory):
    raw = b'<rss><channel><item><title>Show HN: Example product</title><link>https://example.org/product</link><comments>https://news.ycombinator.com/item?id=123</comments></item><item><title>Other story</title><link>https://example.org/story</link></item></channel></rss>'
    class Web:
        proxy_hosts = set()
        def get(self, url):
            return raw, url
    with factory.begin() as session:
        session.add(RegistrySource(id="show-hn-rss", name="Show HN", url="https://hnrss.org/show", enabled=True, collection_method="RSS", options={"link_pattern": "^https://news.ycombinator.com"}))
    discovery = Discovery(settings, Web(), factory=factory)
    with factory() as session:
        source = session.get(RegistrySource, "show-hn-rss")
        links = discovery.collect(source, now_utc(), archive=False)
    assert len(links) == 1
    assert links[0]["url"] == "https://example.org/product"
    assert links[0]["discovery_url"] == "https://news.ycombinator.com/item?id=123"


def test_source_restricted_run_preserves_other_source_queue(settings, factory):
    first = sample_article("AgroKo‘mak", "https://news.example/first")
    second = sample_article("SecondProject", "https://news.example/second")
    first.source_id, second.source_id = "source-a", "source-b"
    with factory.begin() as session:
        for source_id in ("source-a", "source-b"):
            session.add(RegistrySource(id=source_id, name=source_id, url=f"https://{source_id}.example/rss", enabled=True))
    class AttributedDiscovery(FakeDiscovery):
        def discover(self, now, archive=False):
            return [{"url": article.url, "source_id": article.source_id} for article in self.articles], [], 2
    discovery = AttributedDiscovery([first, second])
    discovery.allowed_source_ids = {"source-a"}
    result = Pipeline(settings, factory, discovery, FakeAnalyzer()).run()
    assert result["counts"]["candidates"] == 1
    with factory() as session:
        assert session.get(Candidate, first.url).status == "published"
        assert session.get(Candidate, second.url).status == "queued"


def test_global_primary_page_keeps_international_identity_and_waits_for_translation(settings, factory):
    article = sample_article("Leafovers", "https://leafovers.example/")
    article.title = "Leafovers — Telegram lead inbox"
    article.discovery_title = "Show HN: Leafovers – Telegram lead inbox"
    article.discovery_url = "https://news.ycombinator.com/item?id=123"
    article.source_id = "show-hn-rss"
    article.text = "Leafovers was built by Alice Smith. Small businesses lose Telegram messages from customers. Leafovers automates the inbox for businesses."
    analysis = ExtractiveAnalyzer().analyze([article])
    assert analysis is not None
    assert analysis.country == "International"
    assert not analysis.uzbekistan_related
    assert analysis.main_url == article.url
    with factory.begin() as session:
        session.add(RegistrySource(id="show-hn-rss", name="Show HN", url="https://hnrss.org/show", enabled=True, collection_method="RSS"))
    result = Pipeline(settings, factory, FakeDiscovery([article])).run()
    assert result["counts"]["new_projects"] == 0
    with factory() as session:
        project = session.scalar(select(Project))
        if project:
            assert project.country == "International"
            assert project.publication_status != "PUBLISHED"
            assert project.main_url == article.url
            assert project.discovery_source_url == article.discovery_url


def test_irrelevant_historical_signals_are_retained_but_ignored(settings, factory):
    from backend.app.signal_quality import audit_signals
    with factory.begin() as session:
        session.add(EcosystemSignal(url="https://news.example/scholarship", title="Polsha magistratura stipendiyasi", quote="Polsha magistratura stipendiyasi", summary_uz="Talabalar uchun stipendiya", country="Uzbekistan", signal_type="PROGRAM", published_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    audit_signals(factory)
    with factory() as session:
        row = session.scalar(select(EcosystemSignal))
        assert row is not None and row.intelligence_status == "IGNORED"
