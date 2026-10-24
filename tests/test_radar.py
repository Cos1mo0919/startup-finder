from tests.admin_key import ADMIN_KEY
from zoneinfo import ZoneInfo
from datetime import timedelta
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from backend.app.collectors.sources import Discovery
from backend.app.db import (
    EcosystemSignal,
    Event,
    Project,
    RegistrySource,
    now_utc,
)
from backend.app.registry import SourceConfig, due, record_check, seed_registry
from backend.app.evidence import evidence_score
from backend.app.detection import material_type
from backend.app.events import detect_event, event_queries
from backend.app.main import create_app
from backend.app.network import FetchError
from backend.app.pipeline import Pipeline
from backend.app.sectors import classify_sectors
from tests.conftest import FakeAnalyzer, FakeDiscovery, sample_analysis, sample_article


def setup_source(settings, factory, **overrides):
    source = {
        "id": "test-source",
        "name": "Test University",
        "url": "https://news.example/rss",
        "kind": "university",
        "source_type": "university",
        "priority": 5,
        "enabled": True,
        "collection_method": "RSS",
        "reliability_score": 9,
        **overrides,
    }
    settings.sources_file.write_text(json.dumps([source]))
    seed_registry(factory, settings.sources_file)
    return source


@pytest.mark.parametrize("priority,minutes", [(5, 60), (4, 180), (3, 480), (2, 1440), (1, 10080)])
def test_priority_defaults_and_due(priority, minutes):
    config = SourceConfig(name="Example", url="https://example.uz/rss", priority=priority)
    assert config.check_frequency == minutes
    now = now_utc()
    source = SimpleNamespace(enabled=True, last_checked_at=now, check_frequency=minutes)
    assert not due(source, now + timedelta(minutes=minutes - 1))
    assert due(source, now + timedelta(minutes=minutes))
    source.enabled = False
    assert not due(source, now + timedelta(days=20), force=True)


def test_explicit_frequency_and_seed_preserve_operator_changes(settings, factory):
    setup_source(settings, factory, priority=3, check_frequency=720)
    with factory.begin() as session:
        source = session.get(RegistrySource, "test-source")
        source.enabled = False
        source.consecutive_errors = 3
    assert seed_registry(factory, settings.sources_file) == 0
    with factory() as session:
        source = session.get(RegistrySource, "test-source")
        assert source.enabled is False and source.check_frequency == 720
    seed_registry(factory, settings.sources_file, update=True)
    with factory() as session:
        source = session.get(RegistrySource, "test-source")
        assert source.enabled and source.consecutive_errors == 3


def test_source_health_success_failure_recovery(settings, factory):
    setup_source(settings, factory)
    now = now_utc()
    record_check(factory, "test-source", now, count=5)
    record_check(factory, "test-source", now + timedelta(hours=1), error="http_503")
    record_check(factory, "test-source", now + timedelta(hours=2), error="http_503")
    with factory() as session:
        source = session.get(RegistrySource, "test-source")
        assert source.consecutive_errors == 2 and source.last_success_at is not None
    record_check(factory, "test-source", now + timedelta(hours=3), count=2)
    with factory() as session:
        assert session.get(RegistrySource, "test-source").consecutive_errors == 0


class FakeWeb:
    def __init__(self, raw=b"<rss><channel></channel></rss>"):
        self.raw = raw
        self.calls = []
        self.proxy_hosts = set()

    def get(self, url):
        self.calls.append(url)
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw, url


def test_discovery_only_checks_due_sources(settings, factory):
    setup_source(settings, factory)
    web = FakeWeb()
    discovery = Discovery(settings, web, factory=factory)
    now = now_utc()
    assert discovery.discover(now)[2] == 1
    assert discovery.discover(now + timedelta(minutes=30))[2] == 0
    assert discovery.discover(now + timedelta(hours=1))[2] == 1
    assert len(web.calls) == 2


def test_discovery_errors_persist_health(settings, factory):
    setup_source(settings, factory)
    discovery = Discovery(settings, FakeWeb(FetchError("http_403")), factory=factory)
    result = discovery.discover(now_utc())
    assert result[1][0]["code"] == "http_403"
    with factory() as session:
        assert session.get(RegistrySource, "test-source").consecutive_errors == 1


def test_direct_page_adapter_filters_links_without_new_code(settings, factory):
    setup_source(settings, factory, collection_method="direct_page", options={"link_pattern": "/project/"})
    web = FakeWeb(
        b'<a href="/project/1">Project</a><a href="/login">Login</a><a href="https://other.example/project/2">External</a>'
    )
    items, errors, _ = Discovery(settings, web, factory=factory).discover(now_utc())
    assert not errors and len(items) == 1 and items[0]["url"] == "https://news.example/project/1"


def test_missing_key_is_visible_configuration_state(settings, factory):
    setup_source(
        settings,
        factory,
        collection_method="search",
        options={"query": "Uzbekistan {region} startup", "regions": ["Samarqand"]},
    )
    Discovery(settings, FakeWeb(), factory=factory).discover(now_utc())
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/admin/sources", headers={"X-Admin-Key": ADMIN_KEY}).json()[0]["status"] == "NEEDS_CONFIG"


def test_stop_filter_hides_unknown_creator_and_records_reasons(settings, factory):
    article = sample_article()
    analysis = sample_analysis(article)
    analysis.creator = ""
    Pipeline(settings, factory, FakeDiscovery([])).persist(analysis, [article], now_utc())
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects?period=all").json()["total"] == 0
        status = client.get("/api/admin/status", headers={"X-Admin-Key": ADMIN_KEY}).json()
        assert status["evidence_summary"]["hidden_projects"] == 1
        assert "Muallif yoki jamoa tasdiqlanmagan" in status["rejected_candidates"][0]["reason_labels"]
        hidden = status["project_debug"][0]["id"]
        assert client.get("/api/projects/" + hidden).status_code == 404


def test_low_confidence_project_is_hidden(settings, factory):
    setup_source(settings, factory, reliability_score=0, kind="unknown")
    article = sample_article()
    result = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run()
    assert result["counts"]["pending"] == 1
    with factory() as session:
        project = session.scalar(select(Project))
        assert not project.visible and "low_evidence" in project.stop_reasons
        assert project.publication_status == "REVIEW_REQUIRED"


def test_evidence_roles_and_breakdown_are_separate_from_usefulness(settings, factory):
    setup_source(settings, factory)
    article = sample_article()
    analysis = sample_analysis(article)
    Pipeline(settings, factory, FakeDiscovery([])).persist(analysis, [article], now_utc())
    with factory() as session:
        p = session.scalar(select(Project))
        assert p.visible
        assert {"creator_identity", "project_exists", "university_confirmation"} <= {
            e.evidence_type for e in p.evidence_records
        }
        assert round(sum(c["score"] for c in p.confidence_components.values()), 2) == p.confidence
        assert p.confidence != p.rating
        assert all(e.source_id == "test-source" and e.quote in article.text for e in p.evidence_records)


def test_syndicated_quotes_do_not_inflate_independent_sources():
    registry = {"a": SimpleNamespace(reliability_score=8), "b": SimpleNamespace(reliability_score=8)}
    first = SimpleNamespace(
        source_id="a",
        url="https://first.uz/p",
        quote="Project launch quote same text",
        evidence_type="project_exists",
    )
    second = SimpleNamespace(
        source_id="b", url="https://second.uz/p", quote=first.quote, evidence_type="project_exists"
    )
    assert evidence_score([first, second], registry)[1]["independence"]["score"] == 0
    second.quote = "A separately reported project demonstration confirmed today"
    assert evidence_score([first, second], registry)[1]["independence"]["score"] > 0.0


@pytest.mark.parametrize(
    "title,kind",
    [
        ("10 startup ideas for Uzbekistan", "REJECT"),
        ("New startup fund in Uzbekistan", "ECOSYSTEM_SIGNAL"),
        ("IT Park Uzbekistan expansion announced", "ECOSYSTEM_SIGNAL"),
    ],
)
def test_material_classification(title, kind):
    a = sample_article()
    a.title = title
    assert material_type(a) == kind


def test_ecosystem_signal_saved_but_never_published(settings, factory):
    a = sample_article()
    a.title = "New startup fund in Uzbekistan"
    result = Pipeline(settings, factory, FakeDiscovery([a]), FakeAnalyzer()).run()
    assert result["counts"]["ecosystem_signals"] == 1
    with factory() as session:
        assert session.get(EcosystemSignal, a.url)
        assert not session.scalars(select(Project)).all()


def test_event_detection_and_multilingual_followup_queries():
    a = sample_article()
    a.title = "“Samarqand AI Hackathon” tanlovi"
    a.text = "Samarqand AI Hackathon O‘zbekiston talabalari uchun tanlov. 2026-10-10 dan 2026-10-11 gacha."
    event = detect_event(a)
    assert event["name"] == "Samarqand AI Hackathon" and event["city"] == "Samarqand"
    assert event["start_date"].astimezone(ZoneInfo("Asia/Tashkent")).day == 10
    queries = event_queries(SimpleNamespace(**event))
    assert (
        len(queries) == 9 and any("winner" in q for q in queries) and any("победители" in q for q in queries)
    )


def test_event_to_project_discovery_links_and_persists_provenance(settings, factory):
    setup_source(settings, factory)
    with factory.begin() as session:
        event = Event(
            name="Samarqand AI Hackathon",
            event_type="hackathon",
            source_url="https://news.example/event",
            official_url="https://news.example/event",
            source_id="test-source",
            evidence_quote="Samarqand AI Hackathon",
        )
        session.add(event)
        session.flush()
        event_id = event.id

    class Search:
        def __init__(self):
            self.queries = []

        def search(self, q, freshness="pm"):
            self.queries.append(q)
            return ["https://news.example/project/demo"]

    search = Search()
    discovery = Discovery(settings, FakeWeb(), search=search, factory=factory)
    links, errors = discovery.follow_events(now_utc())
    assert not errors and len(search.queries) == 9
    assert all(i["event_id"] == event_id for i in links)
    article = sample_article(url=links[0]["url"])
    article.event_id = event_id
    article.source_id = "test-source"
    pipe = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer())
    assert pipe.run()["counts"]["event_projects"] == 1
    with factory() as session:
        assert session.scalar(select(Project)).event_id == event_id
    assert discovery.follow_events(now_utc())[0] == []


def test_multi_sector_filters_stats_exclude_hidden(settings, factory):
    a = sample_article()
    analysis = sample_analysis(a)
    analysis.sectors = ["ai", "agritech"]
    Pipeline(settings, factory, FakeDiscovery([])).persist(analysis, [a], now_utc())
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects?period=all&category=ai").json()["total"] == 1
        stats = client.get("/api/sectors/stats", headers={"X-Admin-Key": ADMIN_KEY}).json()
        assert stats["total_projects"] == 1
        assert next(s for s in stats["items"] if s["sector"] == "ai")["count"] == 1
        assert next(s for s in stats["items"] if s["sector"] == "agritech")["count"] == 1


def test_problem_score_does_not_change_usefulness():
    from backend.app.ranking import score

    analysis = sample_analysis()
    article = sample_article()
    original = score(analysis, [article])[0]
    analysis.problem_analysis.problem_severity_score = 10
    assert score(analysis, [article])[0] == original
    assert classify_sectors(analysis)[0] == "agritech"


def test_future_prototype_claim_cannot_pass_stop_filter(settings, factory):
    article = sample_article()
    article.text = (
        "Test University developed plans in Uzbekistan: AgroKo‘mak prototype will be launched in 2028."
    )
    analysis = sample_analysis()
    analysis.facts[0].quote = article.text
    Pipeline(settings, factory, FakeDiscovery([])).persist(analysis, [article], now_utc())
    with factory() as session:
        project = session.scalar(select(Project))
        assert not project.visible and "existence_unconfirmed" in project.stop_reasons


def test_legacy_database_migration_preserves_ids_dates_quotes_and_backup(tmp_path):
    import sqlite3
    import json
    from backend.app.db import make_db, Source
    from backend.app.evidence import audit_existing

    path = tmp_path / "legacy.sqlite3"
    article = sample_article()
    analysis = sample_analysis(article)
    timestamp = now_utc().replace(tzinfo=None).isoformat(" ")
    with sqlite3.connect(path) as connection:
        connection.executescript("""
        CREATE TABLE projects(id VARCHAR(36) PRIMARY KEY,name VARCHAR(200),normalized_project_name VARCHAR(200),
          creator VARCHAR(300),organization VARCHAR(300),country VARCHAR(100),city VARCHAR(100),event VARCHAR(300),
          main_url TEXT,fingerprint VARCHAR(64),aliases JSON,first_seen DATETIME,last_seen DATETIME,
          published_at DATETIME,category VARCHAR(50),audience VARCHAR(30),content JSON,images JSON,
          rating FLOAT,confidence FLOAT,rating_components JSON,confidence_components JSON);
        CREATE TABLE sources(id INTEGER PRIMARY KEY, project_id VARCHAR(36) REFERENCES projects(id),url TEXT UNIQUE,
          publisher VARCHAR(300),kind VARCHAR(30),published_at DATETIME,retrieved_at DATETIME,quotes JSON);
        """)
        connection.execute(
            "INSERT INTO projects VALUES(" + ",".join("?" * 22) + ")",
            (
                "legacy-id",
                analysis.name,
                "agrokomak",
                analysis.creator,
                "",
                "Uzbekistan",
                "",
                "",
                None,
                "fingerprint",
                "[]",
                timestamp,
                timestamp,
                timestamp,
                "agriculture",
                "individual",
                analysis.model_dump_json(),
                "[]",
                3.1,
                3.5,
                "{}",
                "{}",
            ),
        )
        connection.execute(
            "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
            (
                1,
                "legacy-id",
                article.url,
                article.publisher,
                "news",
                timestamp,
                timestamp,
                json.dumps([article.text]),
            ),
        )
    engine, factory = make_db("sqlite:///" + str(path))
    audit_existing(factory, 5)
    with factory() as session:
        p = session.get(Project, "legacy-id")
        assert p and p.first_seen.isoformat(" ") == timestamp
        assert p.sources[0].quotes == [article.text]
        assert session.get(Source, 1).url == article.url
        assert p.visible and p.evidence_records
    engine.dispose()
    assert path.with_name(path.name + ".pre-radar-backup").exists()
    engine, factory = make_db("sqlite:///" + str(path))
    audit_existing(factory, 5)
    with factory() as session:
        assert len(session.scalars(select(Project)).all()) == 1
        assert session.execute(text("SELECT version FROM schema_migrations")).scalar() == 2
    engine.dispose()


def test_acquisition_is_ecosystem_and_grant_competition_is_event():
    article = sample_article()
    article.title = "Company acquires Uzbekistan technology company"
    assert material_type(article) == "ECOSYSTEM_SIGNAL"
    article.title = "O‘zbekistonda grant tanlovi"
    assert detect_event(article)["event_type"] == "grant_competition"
