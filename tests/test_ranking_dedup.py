from backend.app.dedup import find_duplicate, semantic_similarity
from backend.app.pipeline import Pipeline
from backend.app.ranking import confidence, score
from backend.app.schemas import Evidence
from backend.app.db import now_utc, Project
from sqlalchemy import select
from tests.conftest import FakeDiscovery, sample_analysis, sample_article


def test_rating_is_formal_and_bounded():
    article, analysis = sample_article(), sample_analysis()
    analysis.evidence = Evidence(
        practical="in_use",
        practical_fact=0,
        problem="demonstrated",
        problem_fact=0,
        audience="multiple",
        audience_fact=0,
        innovation="novel",
        innovation_fact=0,
        usability="adopted",
        usability_fact=0,
    )
    article.kind = "official"
    total, parts = score(analysis, [article])
    assert total == 10
    assert sum(v["score"] for v in parts.values()) == total
    analysis.evidence.practical_fact = 99
    assert score(analysis, [article])[0] == 7.5


def test_unknown_criteria_receive_zero():
    analysis = sample_analysis()
    analysis.evidence = Evidence()
    total, parts = score(analysis, [sample_article()])
    assert total == 0.6
    assert all(v["score"] == 0 for k, v in parts.items() if k != "source")


def test_confidence_does_not_count_same_publisher_twice():
    a, analysis = sample_article(), sample_analysis()
    b = a.model_copy(update={"url": "https://other.news.example/second"})
    assert confidence(analysis, [a])[0] == confidence(analysis, [a, b])[0]
    b.url = "https://university.uz/project"
    assert confidence(analysis, [a, b])[0] > confidence(analysis, [a])[0]


def test_merge_sources_preserves_first_seen(settings, factory):
    pipe = Pipeline(settings, factory, discovery=FakeDiscovery([]))
    a = sample_article()
    first = now_utc()
    assert pipe.persist(sample_analysis(a), [a], first)
    b = sample_article(url="https://university.uz/news")
    assert not pipe.persist(sample_analysis(b), [b], now_utc())
    with factory() as session:
        projects = session.scalars(select(Project)).all()
        assert len(projects) == 1
        assert len(projects[0].sources) == 2
        assert projects[0].first_seen.isoformat() == first.replace(tzinfo=None).isoformat()
        assert len(projects[0].content["facts"]) == 2


def test_same_creator_different_project_is_new(settings, factory):
    pipe = Pipeline(settings, factory, discovery=FakeDiscovery([]))
    a, b = sample_article(), sample_article("MedYordam", "https://news.example/second")
    assert pipe.persist(sample_analysis(a), [a], now_utc())
    assert pipe.persist(sample_analysis(b, "MedYordam"), [b], now_utc())


def test_same_name_different_creator_does_not_merge(settings, factory):
    pipe = Pipeline(settings, factory, discovery=FakeDiscovery([]))
    a = sample_article()
    pipe.persist(sample_analysis(a), [a], now_utc())
    analysis = sample_analysis()
    analysis.creator = "different team"
    with factory() as session:
        assert find_duplicate(session, analysis, ["https://other.example/x"]) is None


def test_canonical_source_url_deduplicates(settings, factory):
    pipe = Pipeline(settings, factory, discovery=FakeDiscovery([]))
    a = sample_article()
    pipe.persist(sample_analysis(a), [a], now_utc())
    with factory() as session:
        assert find_duplicate(session, sample_analysis(), [a.url + "?utm_source=rss"]) is not None


def test_local_vector_similarity():
    assert semantic_similarity("tibbiyot klinika tashxis", "klinika tashxis tibbiyot") > 0.99
    assert semantic_similarity("tibbiyot klinika", "qishloq paxta") == 0


def test_duplicate_without_named_creator_requires_close_descriptions(settings, factory):
    a = sample_article()
    analysis = sample_analysis(a)
    analysis.creator = ""
    pipe = Pipeline(settings, factory, discovery=FakeDiscovery([]))
    pipe.persist(analysis, [a], now_utc())
    b = sample_article(url="https://second.example/project")
    analysis = sample_analysis(b)
    analysis.creator = ""
    assert not pipe.persist(analysis, [b], now_utc())


def test_numbered_products_are_distinct(settings, factory):
    a = sample_article("Medical Platform 1")
    b = sample_article("Medical Platform 2", "https://news.example/second")
    pipe = Pipeline(settings, factory, discovery=FakeDiscovery([]))
    assert pipe.persist(sample_analysis(a, "Medical Platform 1"), [a], now_utc())
    assert pipe.persist(sample_analysis(b, "Medical Platform 2"), [b], now_utc())
