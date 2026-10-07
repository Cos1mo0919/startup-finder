from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from backend.app.analysis import ExtractiveAnalyzer
from backend.app.collectors.parsers import parse_article
from backend.app.collectors.sources import Discovery
from backend.app.db import Candidate, Project
from backend.app.detection import material_type
from backend.app.fallback import pending_reason
from backend.app.pipeline import Pipeline
from backend.app.ranking import score
from tests.conftest import sample_article, FakeDiscovery


@pytest.mark.parametrize("kind", ["university", "event", "official", "news"])
@pytest.mark.parametrize(
    "text",
    [
        "O‘zbekiston uchun AquaSense platformasi Ali Karimov tomonidan ishlab chiqildi. Ushbu yangi loyiha fermerlar uchun suv muammosini hal qilish imkonini beradi. Prototip taqdim etildi.",
        "В Узбекистане Иван Петров разработал проект “AquaSense” и представил прототип для фермеров.",
        "In Uzbekistan John Smith developed a project “AquaSense” and presented a prototype for farmers.",
    ],
)
def test_real_extractor_publishes_without_ai(settings, factory, kind, text):
    article = sample_article("AquaSense")
    article.text = text
    article.kind = kind
    result = Pipeline(settings, factory, FakeDiscovery([article])).run()
    assert result["counts"]["new_projects"] == 1
    assert result["counts"]["processed_ai"] == 0
    with factory() as session:
        p = session.scalar(select(Project))
        assert p.visible and p.creator and p.confidence >= settings.evidence_min_score
        assert p.content["rating_method"] == "deterministic_fallback"
        assert not p.content["ai_analysis_uz"]
        identity, first_seen = p.id, p.first_seen
    # New independent source, same named/attributed project; archive stays untouched.
    article.url = "https://second.example/project"
    article.published_at = datetime(2023, 6, 1, tzinfo=timezone.utc)
    Pipeline(settings, factory, FakeDiscovery([article])).run(archive=True)
    with factory() as session:
        rows = list(session.scalars(select(Project)))
        assert len(rows) == 1 and rows[0].id == identity and rows[0].first_seen == first_seen
        assert len(rows[0].sources) == 2


def test_missing_creator_stays_pending_with_reason(settings, factory):
    a = sample_article("ClearApp")
    a.text = "O‘zbekiston uchun “ClearApp” loyihasi ishlab chiqildi. Ushbu yangi loyiha talabalar uchun prototip sifatida taqdim etildi."
    result = Pipeline(settings, factory, FakeDiscovery([a])).run()
    assert result["counts"]["pending"] == 1
    with factory() as s:
        c = s.scalar(select(Candidate))
        assert c.reason == "missing_creator"
        assert s.scalar(select(Project)) is None


def test_fallback_rating_only_uses_supported_fields():
    a = sample_article("AquaSense")
    a.text += " Ushbu loyiha talabalar uchun suv muammosini hal qilish imkonini beradi."
    result = ExtractiveAnalyzer().analyze([a])
    value, components = score(result, [a])
    assert 0 < value <= 10 and components["problem"]["score"] == 1
    assert components["innovation"]["score"] == 0
    assert result.problem_uz in a.text
    assert result.rating_method == "deterministic_fallback"


@pytest.mark.parametrize(
    "title",
    [
        "Direktor lavozimiga tayinlandi",
        "Toshkentda kompaniyalar uchrashuvi",
        "Yangi tariflar va jarimalar",
        "10 startup ideas for Uzbekistan",
    ],
)
def test_ordinary_news_rejected(title):
    a = sample_article()
    a.title = title
    a.text = "O‘zbekiston kompaniyalari yangi loyiha imkoniyatlarini muhokama qildi."
    assert material_type(a) == "REJECT"


def test_editorial_series_is_not_product():
    a = sample_article()
    a.text = "Spot “Ryukzakda nima bor?” nomli loyihani davom ettiradi. Intervyuda Ali Karimov yaratgan dastur haqida ham gap bor."
    assert material_type(a) == "REJECT"


def test_uzhunt_body_does_not_use_recommendation_and_parses_full_date():
    a = parse_article(
        """<html lang="uz"><h1>RealApp</h1><p class="cite-date">6-oktabr 2026</p><div class="pmain">RealApp description<article>Unrelated recommended product</article></div></html>""",
        "https://uzhunt.uz/p/real",
        options={"body_selector": ".pmain", "date_selector": ".cite-date", "exclude_selectors": ["article"]},
    )
    assert a.published_at.year == 2026 and a.published_at.month == 10
    assert "Unrelated" not in a.text and "RealApp" in a.text


def test_event_links_match_labels_without_search_api(settings):
    class Web:
        def get(self, url):
            return (
                b'<a href="/n/12">Hackathon winners and projects</a><a href="https://other.example/projects">Other</a>',
                url,
            )

    discovery = Discovery(settings, Web())
    result = discovery.page_links("https://event.example/", "winner|project", match_text=True)
    assert [r["url"] for r in result] == ["https://event.example/n/12"]


def test_pending_ambiguity_is_explicit():
    a = sample_article()
    a.text = "O‘zbekiston uchun yangi loyiha ishlab chiqildi."
    a.title = "Yangi loyiha"
    assert pending_reason(a) == "ambiguous_project"


def test_company_launch_has_creator_evidence(settings, factory):
    a = sample_article("Uzbekistan Airways")
    a.text = "“Uzbekistan Airways” aviachiptalarni xarid qilish uchun mobil ilovani ishga tushirdi. Ushbu yangi ilova yo‘lovchilar uchun joy tanlash imkonini beradi."
    result = Pipeline(settings, factory, FakeDiscovery([a])).run()
    assert result["counts"]["new_projects"] == 1
    with factory() as s:
        p = s.scalar(select(Project))
        assert p.creator == "Uzbekistan Airways" and p.visible


def test_empty_title_meta_uses_article_heading():
    article = parse_article(
        '<html><meta property="og:title" content=""><h1>Actual project</h1><article>Real article text</article></html>',
        "https://news.example/article",
    )
    assert article.title == "Actual project"


def test_itpark_origin_is_not_generic_accelerator():
    from types import SimpleNamespace
    from backend.app.collectors.sources import source_origin

    source = SimpleNamespace(
        collection_method="direct_page",
        source_type="accelerator",
        url="https://www.it-park.uz/uz/itpark/news",
    )
    assert source_origin(source) == "it_park"


def test_financing_program_does_not_borrow_unrelated_university_creator():
    from backend.app.fallback import extract

    a = sample_article("Ko‘mak")
    a.title = "Ta’lim markazlari uchun yordam"
    a.text = "O‘zbekistonda Ko‘mak loyihasi qo‘llab-quvvatlanmoqda. Ko‘mak dasturi doirasida 130 mln so‘m ssuda ajratildi. Test universiteti boshqa tizimni ishlab chiqdi."
    assert material_type(a) == "ECOSYSTEM_SIGNAL"
    assert extract(a) is None


def test_creator_must_belong_to_named_product():
    from backend.app.fallback import extract

    a = sample_article("AquaSense")
    a.text = "O‘zbekiston uchun AquaSense platformasi ishga tushirildi. Ali Karimov boshqa ilovani yaratdi. Ushbu yangi loyiha haqida xabar berildi."
    assert extract(a) is None


def test_unrelated_future_plan_does_not_veto_actual_launch(settings, factory):
    a = sample_article("Uzbekistan Airways")
    a.text = "“Uzbekistan Airways” aviachiptalarni xarid qilish uchun mobil ilovani ishga tushirdi. Ushbu yangi ilova yo‘lovchilar uchun joy tanlash imkonini beradi. Avvalroq boshqa aeroport qurilishi rejalashtirilayotgani haqida yozgandik."
    result = Pipeline(settings, factory, FakeDiscovery([a])).run()
    assert result["counts"]["new_projects"] == 1
    with factory() as s:
        assert s.scalar(select(Project)).visible


def test_drain_does_not_rediscover_events(settings, factory):
    class DiscoveryWithoutNetwork(FakeDiscovery):
        def follow_events(self, now):
            raise AssertionError("drain must not make event discovery requests")

    result = Pipeline(settings, factory, DiscoveryWithoutNetwork([])).run(discover=False)
    assert result["counts"]["sources_checked"] == 0


def test_recruitment_competition_is_not_project_event(settings, factory):
    a = sample_article()
    a.title = "Universitet vakant lavozim uchun tanlov e’lon qiladi"
    a.text = "O‘zbekiston universitetida vakant lavozim uchun tanlov. Yangi ish o‘rni."
    result = Pipeline(settings, factory, FakeDiscovery([a])).run()
    assert result["counts"]["events"] == 0 and result["counts"]["rejected"] == 1


def test_pending_retry_does_not_count_stale_rejection(factory):
    from backend.app.db import Candidate, RejectedCandidate
    from backend.app.diagnostics import candidate_diagnostics

    with factory.begin() as session:
        session.add(
            Candidate(
                url="https://news.example/retry", status="pending", reason="missing_creator", article={}
            )
        )
        session.add(
            RejectedCandidate(url="https://news.example/retry", title="Retry", reasons=["not_project"])
        )
    with factory() as session:
        stats = candidate_diagnostics(session)
        assert not any(r["reason"] == "not_project" for r in stats["reject_reason_stats"])
        assert stats["pending_reason_stats"]["missing_creator"] == 1
