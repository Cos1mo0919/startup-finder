from tests.admin_key import ADMIN_KEY
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import json
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from fastapi.testclient import TestClient
from backend.app.analysis import ExtractiveAnalyzer, AnalysisError
from backend.app.collectors.sources import Discovery
from backend.app.collectors.parsers import parse_article
from backend.app.db import Candidate, Project, now_utc
from backend.app.detection import material_type
from backend.app.events import event_queries
from backend.app.main import create_app
from backend.app.pipeline import Pipeline
from backend.app.queries import archive_windows, targeted_queries, in_window
from backend.app.registry import seed_registry
from tests.conftest import FakeDiscovery, FakeAnalyzer, sample_article, sample_analysis


def test_year_windows_and_inclusive_september_end():
    windows = archive_windows()
    assert [w[0].year for w in windows] == [2022, 2023, 2024, 2025, 2026]
    assert windows[-1] == (date(2026, 1, 1), date(2026, 9, 30))
    assert in_window(datetime.fromisoformat("2026-09-30T23:59:59+05:00"), windows[-1])
    assert not in_window(datetime.fromisoformat("2026-10-01T00:00:00+05:00"), windows[-1])
    with pytest.raises(ValueError):
        archive_windows(date(2021, 1, 1))


def test_queries_cover_languages_projects_regions_and_event_year():
    queries = targeted_queries("Samarqand", 2023)
    assert all("Samarqand" in q and "2023" in q for q in queries)
    for token in ["talaba", "хакатон", "prototype", "demo day"]:
        assert any(token in q for q in queries)
    q = event_queries(SimpleNamespace(name="Regional Hackathon"), (date(2022, 1, 1), date(2022, 12, 31)))
    assert all("2022" in x for x in q)
    assert any("winner" in x for x in q) and any("loyiha" in x for x in q)


@pytest.mark.parametrize(
    "text",
    [
        "O‘zbekiston uchun “AquaSense” loyihasi Ali Karimov tomonidan ishlab chiqildi va talabalar uchun taqdim etildi.",
        "В Узбекистане Иван Петров разработал проект “AquaSense” и представил прототип для фермеров.",
        "In Uzbekistan John Smith developed a project “AquaSense” and presented a prototype for farmers.",
    ],
)
def test_multilingual_fallback_is_evidenced_not_fake_translation(text):
    article = sample_article("AquaSense")
    article.text = text
    result = ExtractiveAnalyzer().analyze([article])
    assert result and result.name == "AquaSense" and result.creator
    assert result.facts[0].quote in text and result.analysis_mode == "extractive"


@pytest.mark.parametrize(
    "title",
    [
        "Toshkentda mehmonxona sotuvga qo‘yildi",
        "Company director appointed in Uzbekistan",
        "IT Park hamkorlik istiqbollarini muhokama qildi",
        "10 startup ideas for Uzbekistan",
    ],
)
def test_noise_does_not_call_expensive_analyzer(settings, factory, title):
    a = sample_article()
    a.title = title
    a.text = "O‘zbekistonda uchrashuv bo‘lib o‘tdi. Yangi loyiha haqida umumiy xabar."

    class Forbidden:
        def analyze(self, articles):
            raise AssertionError("AI must not be called")

    result = Pipeline(settings, factory, FakeDiscovery([a]), Forbidden()).run()
    assert result["counts"]["rejected"] == 1 and not result["errors"]


def test_real_property_technology_is_not_rejected_as_real_estate():
    a = sample_article("BuildSense")
    a.title = "“BuildSense” platformasi binolar uchun ishga tushirildi"
    assert material_type(a) == "PROJECT"
    a.title = "New startup fund in Uzbekistan"
    a.text = "Uzbekistan announced a new fund and investment program."
    assert material_type(a) == "ECOSYSTEM_SIGNAL"


def test_backfill_retains_all_years_and_new_day_does_not_delete(settings, factory, monkeypatch):
    ids = {}
    for year in range(2022, 2027):
        a = sample_article(f"Archive{year}", url=f"https://news.example/{year}")
        a.published_at = datetime(year, 6, 1, tzinfo=timezone.utc)

        class Analyzer:
            def analyze(self, articles):
                return sample_analysis(articles[0], name=f"Archive{year}")

        result = Pipeline(settings, factory, FakeDiscovery([a]), Analyzer()).run(
            window=archive_windows()[year - 2022]
        )
        assert result["counts"]["new_projects"] == 1
    with factory() as session:
        ids = {p.id: p.first_seen for p in session.scalars(select(Project))}
    monkeypatch.setattr("backend.app.pipeline.now_utc", lambda: now_utc() + timedelta(days=2))
    Pipeline(settings, factory, FakeDiscovery([])).run()
    with factory() as session:
        assert {p.id: p.first_seen for p in session.scalars(select(Project))} == ids
    with TestClient(create_app(settings)) as client:
        for year in range(2022, 2027):
            response = client.get(f"/api/projects?period=all&year={year}").json()
            assert response["total"] == 1
            assert response["items"][0]["name"] == f"Archive{year}"


def test_new_source_for_historical_project_merges_without_reset(settings, factory):
    a = sample_article()
    a.published_at = datetime(2023, 5, 1, tzinfo=timezone.utc)
    p = Pipeline(settings, factory, FakeDiscovery([a]), FakeAnalyzer())
    p.run(window=(date(2023, 1, 1), date(2023, 12, 31)))
    with factory() as session:
        old = session.scalar(select(Project))
        identity, seen = old.id, old.first_seen
    b = sample_article(url="https://second.example/current")
    b.text += " Loyiha hozir ham rivojlanmoqda."
    result = Pipeline(settings, factory, FakeDiscovery([b]), FakeAnalyzer()).run()
    assert result["counts"]["duplicates"] == 1
    with factory() as session:
        p = session.scalar(select(Project))
        assert p.id == identity and p.first_seen == seen
        assert len(p.sources) == 2 and len({e.url for e in p.evidence_records}) == 2
        assert p.published_at.year == 2023


def test_queue_preserves_unprocessed_links(settings, factory):
    settings.max_candidates = 1
    articles = [sample_article(f"Queue{i}", url=f"https://news.example/{i}") for i in range(5)]
    pipeline = Pipeline(settings, factory, FakeDiscovery(articles))
    pipeline.run()
    with factory() as session:
        rows = list(session.scalars(select(Candidate)))
        assert len(rows) == 5
        assert sum(c.status == "queued" for c in rows) == 3
    pipeline.run(discover=False)
    with factory() as session:
        assert sum(c.status == "queued" for c in session.scalars(select(Candidate))) == 1


def test_archive_pending_can_upgrade_during_fresh_run_without_duplicate(settings, factory):
    a = sample_article()
    a.published_at = datetime(2022, 6, 1, tzinfo=timezone.utc)

    class Pending:
        def analyze(self, articles):
            return None

    result = Pipeline(settings, factory, FakeDiscovery([a]), Pending()).run(
        window=(date(2022, 1, 1), date(2022, 12, 31))
    )
    assert result["status"] == "partial" and result["details"]["summary"]["pending"] == 1
    settings.ai_api_key = SecretStr("test-only")
    result = Pipeline(settings, factory, FakeDiscovery([]), FakeAnalyzer()).run()
    assert result["counts"]["new_projects"] == 1 and result["counts"]["processed_ai"] == 1
    result = Pipeline(settings, factory, FakeDiscovery([]), FakeAnalyzer()).run()
    with factory() as session:
        assert len(list(session.scalars(select(Project)))) == 1


def test_source_failure_is_isolated_and_status_explains_pending(settings, factory):
    a = sample_article()

    class Broken(FakeDiscovery):
        def discover(self, now, archive=False):
            return (
                [{"url": a.url, "origin": "university"}],
                [{"source": "Blocked university", "stage": "source", "code": "http_403"}],
                2,
            )

    result = Pipeline(settings, factory, Broken([a])).run()
    assert result["status"] == "partial" and result["counts"]["new_projects"] == 1
    assert result["details"]["summary"]["source_errors"] == 1
    with TestClient(create_app(settings)) as client:
        s = client.get("/api/admin/status", headers={"X-Admin-Key": ADMIN_KEY}).json()
        assert s["processing_summary"]["processed_fallback"] == 1
        assert s["origin_stats"][0]["origin"] == "university"
        assert s["last_run"]["details"]["summary"]["source_errors"] == 1


def test_ai_and_translation_errors_remain_retryable(settings, factory):
    settings.ai_api_key = SecretStr("test-only")

    class Broken:
        def analyze(self, articles):
            raise AnalysisError("translation_not_uzbek")

    a = sample_article()
    result = Pipeline(settings, factory, FakeDiscovery([a]), Broken()).run()
    assert result["counts"]["translation_errors"] == 1
    with factory() as session:
        assert session.get(Candidate, a.url).status == "error"
    result = Pipeline(settings, factory, FakeDiscovery([]), FakeAnalyzer()).run()
    assert result["counts"]["new_projects"] == 1


def test_unknown_date_and_noise_rejection_statistics(settings, factory):
    a = sample_article()
    a.published_at = None
    Pipeline(settings, factory, FakeDiscovery([a])).run()
    with TestClient(create_app(settings)) as client:
        data = client.get("/api/admin/status", headers={"X-Admin-Key": ADMIN_KEY}).json()
        assert any(
            r["reason"] == "unknown_publication_date" and r["count"] == 1 for r in data["reject_reason_stats"]
        )


def test_university_parser_uses_explicit_article_date_not_sidebar():
    raw = b'<title>Project</title><aside><time datetime="2026-10-01">Other article</time></aside><div class="stamp">12.06.2023</div><article>Real university project article with source evidence.</article>'
    a = parse_article(
        raw, "https://university.example/a", options={"body_selector": "article", "date_selector": ".stamp"}
    )
    # Configured publication selector must override unrelated generic time tags.
    assert a.published_at.year == 2023
    assert "Other article" not in a.text


def test_disabled_university_remains_disabled_on_seed_and_discovery(settings, factory):
    settings.sources_file.write_text(
        json.dumps(
            [
                {
                    "id": "uni",
                    "name": "Uni",
                    "url": "https://university.example/",
                    "source_type": "university",
                    "enabled": False,
                }
            ]
        )
    )
    seed_registry(factory, settings.sources_file)

    class Forbidden:
        proxy_hosts = set()

        def get(self, url):
            raise AssertionError("Disabled source requested")

    discovery = Discovery(settings, Forbidden(), factory=factory)
    discovery.force = True
    links, errors, checked = discovery.discover(now_utc())
    assert not links and not errors and checked == 0


def test_public_sitemap_stratifies_year_without_using_lastmod(settings):
    from backend.app.collectors.archive import sitemap_links

    class Web:
        def get(self, url):
            if url.endswith("index.xml"):
                return (
                    b"<sitemapindex><sitemap><loc>https://example.uz/2022-01.xml</loc></sitemap><sitemap><loc>https://example.uz/2022-12.xml</loc></sitemap></sitemapindex>",
                    url,
                )
            return (
                b"<urlset><url><loc>https://example.uz/oz/2022/06/01/startup/</loc><lastmod>2026-10-07</lastmod></url><url><loc>https://example.uz/oz/2021/06/01/startup/</loc></url></urlset>",
                url,
            )

    d = SimpleNamespace(web=Web(), archive_cache={}, archive_coverage=[], settings=settings)
    s = SimpleNamespace(id="source")
    result = sitemap_links(
        d,
        s,
        (date(2022, 1, 1), date(2022, 12, 31)),
        {
            "sitemap_index": "https://example.uz/index.xml",
            "sitemap_pattern": "{year}-",
            "target_pattern": "startup",
        },
    )
    assert len(result) == 1 and result[0]["published_at"] is None
    assert d.archive_coverage[0]["pages"] == 2
    assert d.archive_coverage[0]["selected_sitemaps"] == [
        "https://example.uz/2022-01.xml",
        "https://example.uz/2022-12.xml",
    ]


def test_malformed_archive_is_scoped_fetch_error():
    from backend.app.collectors.archive import parse_sitemap
    from backend.app.network import FetchError

    with pytest.raises(FetchError, match="invalid_sitemap"):
        parse_sitemap(b"<not-xml")


def test_year_rediscovery_recovers_article_outside_first_window(settings, factory):
    a = sample_article()
    a.published_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    pipeline = Pipeline(settings, factory, FakeDiscovery([a]), FakeAnalyzer())
    first = pipeline.run(window=(date(2022, 1, 1), date(2022, 12, 31)))
    assert first["details"]["reject_reasons"]["outside_archive_window"] == 1
    second = pipeline.run(window=(date(2025, 1, 1), date(2025, 12, 31)))
    assert second["counts"]["new_projects"] == 1


def test_queued_rss_publication_date_is_retained(settings, factory):
    a = sample_article()

    class Feed(FakeDiscovery):
        def discover(self, now, archive=False):
            return [{"url": a.url, "published_at": a.published_at}], [], 1

        def article(self, url, feed_date=None):
            assert feed_date == a.published_at
            return a

    result = Pipeline(settings, factory, Feed([a]), FakeAnalyzer()).run()
    assert result["counts"]["new_projects"] == 1


def test_verified_managed_proxy_dns_cached_but_new_hosts_validated(settings, monkeypatch):
    import httpx
    from backend.app.network import WebClient

    checked = []

    def dns(url, hosts):
        checked.append(url)
        return False

    monkeypatch.setattr("backend.app.network.public_dns", dns)
    web = WebClient(settings)
    web.proxy_hosts = {"news.example"}
    web.client.close()
    web.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="Article"))
    )
    web.last_request = {}
    monkeypatch.setattr("backend.app.network.time.sleep", lambda _: None)
    web._fetch("https://news.example/one")
    web._fetch("https://news.example/two")
    web._fetch("https://different.example/one")
    assert checked == ["https://news.example/one", "https://different.example/one"]
    web.close()
