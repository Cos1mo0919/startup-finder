from datetime import date, datetime, timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.app.db import Candidate, Problem, ProblemEvidence, Project, ProjectProblemLink, SchedulerCheckpoint, make_db
from backend.app.intelligence import cited_problem_scores, entity_type, opportunity, problem_gate, problem_from_article, upsert_problem
from backend.app.main import create_app
from backend.app.scheduler import make_scheduler, scan_due
from tests.conftest import sample_analysis, sample_article


def test_problem_gate_and_dedup_keep_distinct_evidence(factory):
    a = sample_article(url="https://news.example/one")
    a.text = "O‘zbekiston klinika mijozlari qo‘ng‘iroqlarga javob bo‘lmagani sabab vaqt yo‘qotadi. “AgroKo‘mak” loyihasi klinika qo‘ng‘iroqlarini avtomatlashtiradi. Test University tomonidan ishlab chiqildi."
    b = sample_article(url="https://news.example/two")
    b.text = a.text
    analysis = sample_analysis(a)
    gate, reason, finding = problem_gate(analysis, [a])
    assert (gate, reason) == ("PASS", "source_backed_problem")
    assert "klinika" in finding["statement"]
    assert entity_type(a) == "PROJECT"
    with factory.begin() as session:
        p1 = upsert_problem(session, finding)
        first_id = p1.id
    finding["source_url"] = b.url
    with factory.begin() as session:
        p2 = upsert_problem(session, finding)
        assert p2.id == first_id
    with factory() as session:
        assert len(session.scalars(select(Problem)).all()) == 1
        assert len(session.scalars(select(ProblemEvidence)).all()) == 2


def test_minor_feature_and_unknown_problem_never_strong():
    article = sample_article()
    article.title = "CRM introduces a different button color"
    article.text = "CRM introduces a different button color and new theme."
    assert entity_type(article) == "IGNORE"
    gate, reason, finding = problem_gate(sample_analysis(article), [article])
    assert (gate, reason, finding) == ("REJECT", "minor_feature", None)
    assert opportunity({}, 1, gate)["grade"] == "REJECTED"
    article = sample_article()
    article.text = "Yangi platforma taqdim etildi."
    gate, reason, _ = problem_gate(sample_analysis(article), [article])
    assert (gate, reason) == ("PENDING", "pending_problem_analysis")
    assert opportunity({}, 2, gate)["grade"] == "PENDING"


def test_cited_score_and_evidence_adjustment():
    from backend.app.intelligence import CRITERIA
    inputs = {name: {"score": 5, "reason": "Dalil", "evidence_refs": ["https://news.example/one"], "confidence": "HIGH"}
              for names in CRITERIA.values() for name in names}
    weak = opportunity(inputs, 2)
    strong = opportunity(inputs, 5)
    assert weak["score"] == 60
    assert weak["grade"] == "C"
    assert strong["score"] == 100
    assert strong["grade"] == "A"
    assert opportunity({"pain_strength": inputs["pain_strength"]}, 5)["grade"] == "PENDING"
    assert opportunity(inputs, 5, fatal_reasons=["minor_feature"])["grade"] == "REJECTED"
    without_confidence = {**inputs, "pain_strength": {k: v for k, v in inputs["pain_strength"].items() if k != "confidence"}}
    assert opportunity(without_confidence, 5)["grade"] == "PENDING"


def test_partial_score_keeps_cited_criteria_without_inventing_market():
    finding = {
        "quote": "Jurnalistlar bir soatlik intervyuni matnga o‘tkazish uchun uch soat vaqt sarflagan.",
        "source_url": "https://www.spot.uz/oz/2026/03/10/kotibai",
    }
    criteria = cited_problem_scores(finding)
    assert criteria["pain_strength"]["evidence_refs"] == [finding["source_url"]]
    assert criteria["pain_strength"]["confidence"] == "LOW"
    assert criteria["current_cost"]["score"] == 3
    result = opportunity(criteria, 2, "PASS")
    assert result["criteria"] == criteria
    assert result["score"] is None
    assert result["grade"] == "PENDING"


def test_dmed_prescription_error_is_source_backed_local_problem():
    article = sample_article(name="DMED")
    article.text = (
        "O‘zbekiston uchun DMED platformasi ishlab chiqildi. "
        "DMED tizimi dorixonalarga real vaqt rejimida ma’lumot olish imkonini beradi. "
        "Xalqaro patentlanmagan nomlar bo‘yicha preparatlarni avtomatlashtirilgan tarzda tanlash "
        "orqali retseptni shakllantirishda xatolarni bartaraf etish mumkin."
    )
    analysis = sample_analysis(article, name="DMED")
    gate, reason, finding = problem_gate(analysis, [article])
    assert (gate, reason) == ("PASS", "source_backed_problem")
    assert finding["scope"] == "UZBEKISTAN_LOCAL"
    assert finding["quote"] in article.text
    assert cited_problem_scores(finding)["pain_strength"]["score"] == 3


def test_plant_clinic_does_not_make_agricultural_app_healthtech():
    from backend.app.sectors import classify_sectors

    analysis = sample_analysis()
    analysis.primary_sector = "healthtech"
    analysis.sectors = ["healthtech", "agritech"]
    analysis.category = "other"
    analysis.summary_uz = "Fermerlar o‘simlik klinikalari va agrokimyoviy tahlil haqida ma’lumot oladi."
    assert classify_sectors(analysis) == ("agritech", ["agritech"])


def test_archive_budget_prioritizes_matching_year_and_project_title():
    from backend.app.pipeline import archive_priority

    window = (date(2023, 1, 1), date(2023, 12, 31))
    matching_project = SimpleNamespace(url="https://spot.uz/oz/2023/11/22/app", article={"title": "Yangi loyiha"})
    matching_news = SimpleNamespace(url="https://spot.uz/oz/2023/02/02/news", article={"title": "Yangilik"})
    unknown = SimpleNamespace(url="https://example.org/article", article={"title": "Startup"})
    wrong_year = SimpleNamespace(url="https://spot.uz/oz/2026/04/06/app", article={"title": "Startup"})
    assert sorted([wrong_year, unknown, matching_news, matching_project], key=lambda c: archive_priority(c, window)) == [
        matching_project, matching_news, unknown, wrong_year
    ]


def test_bounded_backfill_processes_matching_year_before_wrong_year(settings, factory):
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeAnalyzer, FakeDiscovery

    settings.max_candidates = 1  # Pipeline processes at most two candidates in this run.
    wrong = [sample_article(url=f"https://news.example/2026/04/0{i}/news") for i in (1, 2)]
    right = sample_article(url="https://news.example/2023/11/22/project")
    right.published_at = datetime(2023, 11, 22, tzinfo=timezone.utc)

    class Discovery(FakeDiscovery):
        def discover(self, now, archive=False):
            return [{"url": a.url, "title": a.title} for a in self.articles], [], 1

    result = Pipeline(settings, factory, Discovery([*wrong, right]), FakeAnalyzer()).run(
        archive=True, window=(date(2023, 1, 1), date(2023, 12, 31))
    )
    with factory() as session:
        assert session.get(Candidate, right.url).status == "published"
        assert sum(session.get(Candidate, a.url).status == "queued" for a in wrong) == 1
    assert result["counts"]["new_projects"] == 1


def test_reconciliation_checkpoint_and_timezone(settings, factory):
    now = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)  # 08:00 Tashkent
    assert scan_due("morning", None, now)
    assert not scan_due("evening", None, now)
    with factory.begin() as session:
        session.add(SchedulerCheckpoint(name="morning", cursor={"slot": "2026-10-07"}))
    with factory() as session:
        assert not scan_due("morning", session.get(SchedulerCheckpoint, "morning"), now)
    engine, again = make_db(settings.database_url)
    with again() as session:
        assert session.get(SchedulerCheckpoint, "morning").cursor["slot"] == "2026-10-07"
    engine.dispose()
    scheduler = make_scheduler(settings, factory)
    assert scheduler.get_job("discovery")
    assert scheduler.get_job("reconciliation")
    assert scan_due("local_weekly", None, now)
    assert scan_due("global_monthly", None, now)


def test_migration_and_read_only_api_preserve_project(settings, factory):
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer
    article = sample_article()
    Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run()
    with factory() as session:
        project = session.scalar(select(Project))
        original = (project.id, project.first_seen, project.published_at)
    app = create_app(settings)
    with TestClient(app) as client:
        dashboard = client.get("/api/intelligence/dashboard").json()
        assert dashboard["total"]["projects"] == 1
        assert dashboard["today"]["sources_checked"] == 1
        assert dashboard["today"]["links_seen"] == 1
        assert dashboard["latest_projects"][0]["id"] == original[0]
        assert dashboard["latest_projects"][0]["affected_users"] == "Talaba"
        assert dashboard["latest_ideas"] == []
        assert client.get("/api/problems").json()["total"] == 1
        assert client.get("/api/ideas").json() == []
        assert client.get("/api/signals").json() == []
        assert client.get("/api/sectors/intelligence").status_code == 200
        assert client.get("/api/problems/nonexistent").status_code == 404
        project_api = client.get("/api/projects/" + original[0]).json()
        assert project_api["problem_gate_status"] == "PASS"
        assert project_api["opportunity_grade"] == "PENDING"
        assert client.get("/api/admin/status", headers={"X-Admin-Key": "test-admin-key"}).json()["problem_gate_counts"]["PASS"] == 1
    with factory() as session:
        project = session.scalar(select(Project))
        assert (project.id, project.first_seen, project.published_at) == original
        assert len(session.scalars(select(ProjectProblemLink)).all()) == 1
        assert session.get(Candidate, article.url).entity_type == "PROJECT"


def test_problem_article_without_project_is_separate():
    article = sample_article()
    article.title = "Klinikalarda qo‘ng‘iroq muammosi"
    article.text = "Klinika mijozlari javobsiz qo‘ng‘iroqlar sabab vaqt yo‘qotadi."
    assert problem_from_article(article)
    assert entity_type(article) == "PROBLEM"


def test_narrow_english_problem_template_retains_original_quote(factory):
    from backend.app.intelligence import problem_fingerprint

    article = sample_article()
    article.title = "Clinic operations"
    article.text = "Private clinics miss calls every day and lose customers."
    finding = problem_from_article(article)
    assert finding["statement"].startswith("Klinikalar")
    assert finding["quote"] == article.text
    assert entity_type(article) == "PROBLEM"
    assert problem_fingerprint(finding["statement"], finding["subject"], finding["scope"]) == problem_fingerprint(
        "Klinika mijozlari qo‘ng‘iroqlarga javob bo‘lmagani sabab vaqt yo‘qotadi", "Klinika", "EVERYDAY"
    )


def test_neutral_queue_order_is_not_a_problem():
    article = sample_article()
    article.title = "Talabalar arizalari tartibi"
    article.text = "Bir xil ustuvorlikka ega talabalar arizalari topshirilgan sanasi va navbati asosida ko‘rib chiqiladi."
    assert problem_from_article(article) is None
    assert entity_type(article) == "IGNORE"


def test_show_hn_submission_without_product_evidence_is_not_verified_project(settings, factory):
    from backend.app.db import EcosystemSignal, RegistrySource
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer

    article = sample_article(url="https://news.ycombinator.com/item?id=123")
    article.title = "Show HN: Example tool | Hacker News"
    article.text = "Show HN: Example tool for developer workflows. Submitted by an HN user."
    article.source_id = "show-hn-test"
    with factory.begin() as session:
        session.add(RegistrySource(id="show-hn-test", name="HN", url="https://hnrss.org/show",
                                   country="International", enabled=True))
    result = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run()
    assert result["counts"]["new_projects"] == 0
    with factory() as session:
        signal = session.scalar(select(EcosystemSignal))
        assert signal is None or signal.intelligence_status == "IGNORED"
        assert not session.scalars(select(Project)).all()


def test_humo_service_failure_is_local_problem():
    article = sample_article()
    article.title = "Ayrim bank ilovalarida HUMO kartalari bilan muammolar"
    article.text = "Ayni damda bir qator bank ilovalarida HUMO kartalari bilan ishlashda uzilishlar kuzatilmoqda."
    finding = problem_from_article(article)
    assert finding["scope"] == "UZBEKISTAN_LOCAL"
    assert finding["quote"] == article.text
    assert finding["statement"].startswith("HUMO")
    assert entity_type(article) == "PROBLEM"


def test_historical_problem_year_uses_evidence_publication(settings, factory):
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer

    article = sample_article()
    article.published_at = datetime(2022, 4, 11, tzinfo=timezone.utc)
    article.title = "Ayrim bank ilovalarida HUMO kartalari bilan muammolar"
    article.title += " — muntazam uzilishlar"
    article.text = "Ayni damda bir qator bank ilovalarida HUMO kartalari bilan ishlashda uzilishlar kuzatilmoqda."
    result = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run(archive=True)
    assert result["counts"]["problems"] == 1
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/problems?year=2022").json()["total"] == 1
        assert client.get("/api/problems?year=2026").json()["total"] == 0
        assert client.get("/api/problems?period=today").json()["total"] == 1
    with factory.begin() as session:
        session.scalar(select(Problem)).first_seen_at = datetime(2022, 4, 11, tzinfo=timezone.utc)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/problems?period=today").json()["total"] == 0
        assert client.get("/api/problems?year=2022").json()["total"] == 1


def test_source_metadata_seed_does_not_restore_operator_flags(settings, factory):
    import json
    from backend.app.db import RegistrySource
    from backend.app.registry import seed_registry

    settings.sources_file.write_text(json.dumps([{
        "id": "problem-source", "name": "Verified example", "url": "https://news.example/feed",
        "enabled": False, "collection_method": "RSS", "provides_problem_signals": True,
        "country": "Uzbekistan", "purpose": "Problem observations",
    }]))
    seed_registry(factory, settings.sources_file)
    with factory.begin() as session:
        source = session.get(RegistrySource, "problem-source")
        source.provides_problem_signals = False
        source.enabled = False
    seed_registry(factory, settings.sources_file)
    with factory() as session:
        source = session.get(RegistrySource, "problem-source")
        assert not source.provides_problem_signals
        assert not source.enabled
        assert source.purpose == "Problem observations"


def test_one_event_article_can_cite_two_distinct_projects(settings, factory):
    from backend.app.db import Source
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer

    article = sample_article()
    article.title = "O‘zbekiston hackathonida ikki loyiha"
    article.text = (
        "O‘zbekiston hackathonida “AgroKo‘mak” loyihasi Test University tomonidan ishlab chiqildi. "
        "“MedYordam” loyihasi Test University tomonidan ishlab chiqildi."
    )
    result = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run()
    with factory() as session:
        projects = session.scalars(select(Project)).all()
        sources = session.scalars(select(Source)).all()
        candidate = session.get(Candidate, article.url)
        assert len(projects) == 2
        assert all(p.visible for p in projects)
        assert {p.name for p in projects} == {"AgroKo‘mak", "MedYordam"}
        assert len(sources) == 2
        assert {s.url for s in sources} == {article.url}
        assert len(candidate.project_ids) == 2
        assert result["counts"]["event_projects"] == 0
        assert all(p.publication_status == "REVIEW_REQUIRED" for p in projects)


def test_keyless_event_report_extracts_named_founder_without_reusing_other_project(settings, factory):
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery

    article = sample_article()
    article.title = "O‘zbekiston Demo Day loyihalari"
    article.text = (
        "O‘zbekiston Demo Day tadbirida loyihalar namoyish etildi. "
        "Navbatdagi loyiha BITO deb nomlanadi. "
        "Loyiha asoschisi Umidjon Po‘latov BITO platformasining yaratilish tarixi haqida so‘zlab berdi. "
        "BITO — kichik biznes uchun savdo va ombor ishlarini birlashtiradigan platforma. "
        "Yana bir loyiha TIZO deb nomlanadi. "
        "Loyiha asoschisi Akmal Karimov TIZO platformasining yaratilish tarixi haqida so‘zlab berdi. "
        "TIZO — fermerlar uchun xo‘jalik ishlarini birlashtiradigan platforma."
    )
    result = Pipeline(settings, factory, FakeDiscovery([article])).run()
    with factory() as session:
        projects = session.scalars(select(Project)).all()
        candidate = session.get(Candidate, article.url)
        assert {p.name for p in projects} == {"BITO", "TIZO"}
        assert {p.creator for p in projects} == {"Umidjon Po‘latov", "Akmal Karimov"}
        assert len(candidate.project_ids) == 2
        assert result["counts"]["event_projects"] == 0
        assert all(p.publication_status == "REVIEW_REQUIRED" for p in projects)


def test_event_report_without_event_word_in_title_still_extracts_project(settings, factory):
    from backend.app.events import detect_event
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery

    article = sample_article()
    article.title = "CEVF’da qanday loyihalar namoyish etildi?"
    article.text = (
        "O‘zbekiston forumida loyihalar namoyish etildi. "
        "Navbatdagi loyiha BITO deb nomlanadi. "
        "Loyiha asoschisi Umidjon Po‘latov BITO platformasining yaratilish tarixi haqida so‘zlab berdi. "
        "BITO — kichik biznes uchun savdo va ombor ishlarini birlashtiradigan platforma."
    )
    assert detect_event(article)["event_type"] == "exhibition"
    result = Pipeline(settings, factory, FakeDiscovery([article])).run()
    with factory() as session:
        project = session.scalar(select(Project))
        assert project.name == "BITO"
        assert project.creator == "Umidjon Po‘latov"
        assert project.event_id
    assert result["counts"]["event_projects"] == 0


def test_event_report_uses_named_forum_for_followup_queries():
    from backend.app.events import detect_event, event_queries

    article = sample_article()
    article.title = "CEVF’da qanday loyihalar namoyish etildi?"
    article.text = (
        "3-aprel kuni Toshkentda Markaziy Yevroosiyo venchur forumi (CEVF) bo‘lib o‘tdi. "
        "Unda O‘zbekiston loyihalari namoyish etildi."
    )
    event = detect_event(article)
    assert event["name"] == "Markaziy Yevroosiyo venchur forumi (CEVF)"
    assert all("Markaziy Yevroosiyo" in q for q in event_queries(type("Event", (), event)()))


def test_event_report_overrides_unrelated_followup_event(settings, factory):
    from backend.app.db import Event, now_utc
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery

    article = sample_article()
    article.title = "CEVF’da qanday loyihalar namoyish etildi?"
    article.text = (
        "O‘zbekiston forumida loyihalar namoyish etildi. "
        "Navbatdagi loyiha BITO deb nomlanadi. "
        "Loyiha asoschisi Umidjon Po‘latov BITO platformasining yaratilish tarixi haqida so‘zlab berdi. "
        "BITO — tadbirkorlar uchun savdo va ombor ishlarini birlashtiradigan platforma."
    )
    with factory.begin() as session:
        stale = Event(
            name="Boshqa tadbir", event_type="competition", organizer="", country="Uzbekistan",
            city="", source_url="https://news.example/unrelated-event", source_id=None,
            evidence_quote="Boshqa tadbir", status="discovered", discovered_at=now_utc(),
        )
        session.add(stale)
        session.flush()
        article.event_id = stale.id
    Pipeline(settings, factory, FakeDiscovery([article])).run()
    with factory() as session:
        project = session.scalar(select(Project))
        own_event = session.get(Event, project.event_id)
        assert own_event.source_url == article.url
        assert own_event.name == article.title


def test_keyless_real_product_lead_and_interview_do_not_capture_advertising():
    from backend.app.fallback import extract, project_name

    article = sample_article(name="Tilmoch")
    article.title = "Tilmoch onlayn tarjimoni investitsiya jalb qildi"
    article.text = (
        "Tilmoch AI uchta venchur fondidan sarmoya jalb qildi. "
        "Bu haqda loyiha asoschisi Muhammadsaid Mamasaidov Spot’ga ma’lum qildi. "
        "Tilmoch AI — o‘zbek va turkiy tillar uchun yaratilgan tarjima platformasi. "
        "Tilmoch startapi O‘zbekiston foydalanuvchilariga xizmat taklif etadi."
    )
    analysis = extract(article)
    assert analysis and analysis.name == "Tilmoch"
    assert analysis.creator == "Muhammadsaid Mamasaidov"
    assert all(f.quote in article.text for f in analysis.facts)

    interview = sample_article(name="Tahrirchi")
    interview.title = "Tahrirchi: startap tarixi"
    interview.text = (
        "Toshkentdagi universitet talabalari “Tahrirchi” loyihasini tuzdi. "
        "Bugungi kunda startap imlo tekshiruvi kabi mahsulotlarga ega. "
        '"Spot.uz"da reklama “Spot” loyiha asoschisi Muhammadsaid Mamasaidov bilan suhbatlashdi. '
        "Jamoa O‘zbekiston uchun ishlab chiqqan mahsulotlardan foydalanmoqda."
    )
    assert project_name(interview) == ["Tahrirchi"]
    analysis = extract(interview)
    assert analysis and analysis.name == "Tahrirchi"
    assert analysis.creator == "Muhammadsaid Mamasaidov"


def test_existing_hidden_project_first_publication_is_counted_as_new(settings, factory):
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer

    article = sample_article()
    Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run()
    with factory.begin() as session:
        project = session.scalar(select(Project))
        original_id = project.id
        project.visible = False
        project.publication_status = "REVIEW_REQUIRED"
        session.get(Candidate, article.url).status = "queued"
    result = Pipeline(settings, factory, FakeDiscovery([]), FakeAnalyzer()).run(archive=True, discover=False)
    assert result["counts"]["new_projects"] == 1, result
    assert result["counts"]["duplicates"] == 0
    with factory() as session:
        assert session.scalar(select(Project)).id == original_id
        assert session.scalar(select(Project)).visible


def test_transcription_pain_quote_links_to_named_solution():
    article = sample_article(name="KotibAI")
    article.title = "KotibAI loyihasi haqida"
    article.text = (
        "KotibAI — o‘zbek tilidagi ovozli xabarlarni matnga o‘giruvchi tizim. "
        "Shunda biz o‘yladik: “Agar bu jarayonda sun’iy intellekt yechim bera olsa-chi?” "
        "Masalan, jurnalistlar bir soatlik intervyuni matnga o‘tkazish uchun uch soat vaqt sarflagan."
    )
    analysis = sample_analysis(article, name="KotibAI")
    gate, _, finding = problem_gate(analysis, [article])
    assert gate == "PASS"
    assert finding["statement"] == "Jurnalistlar bir soatlik intervyuni matnga o‘tkazish uchun uch soat vaqt sarflagan."
    assert finding["quote"] in article.text


def test_old_url_unique_citations_migrate_without_losing_ids(settings, factory):
    import sqlite3
    from pathlib import Path
    from sqlalchemy import inspect
    from backend.app.db import Source
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer

    article = sample_article()
    Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run()
    with factory() as session:
        project = session.scalar(select(Project))
        source = session.scalar(select(Source))
        identity = (project.id, project.first_seen, project.published_at, source.id, source.url)
    path = Path(settings.database_url.removeprefix("sqlite:///"))
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE project_sources_legacy (
            id INTEGER PRIMARY KEY, project_id VARCHAR(36), url TEXT UNIQUE,
            publisher VARCHAR(300), kind VARCHAR(30), published_at DATETIME,
            retrieved_at DATETIME, quotes JSON, source_id VARCHAR(80))""")
        db.execute("""INSERT INTO project_sources_legacy SELECT id,project_id,url,publisher,kind,
            published_at,retrieved_at,quotes,source_id FROM project_sources""")
        db.execute("DROP TABLE project_sources")
        db.execute("ALTER TABLE project_sources_legacy RENAME TO project_sources")
    engine, migrated = make_db(settings.database_url)
    with migrated() as session:
        project = session.scalar(select(Project))
        source = session.scalar(select(Source))
        assert (project.id, project.first_seen, project.published_at, source.id, source.url) == identity
        assert {"project_id", "url"} in [set(c["column_names"]) for c in inspect(engine).get_unique_constraints("project_sources")]
    engine.dispose()
    assert path.with_name(path.name + ".pre-multisource-backup").exists()


def test_pipeline_publishes_source_backed_problem_and_keeps_facts_separate(settings, factory):
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer

    article = sample_article()
    article.text = (
        "O‘zbekiston klinika mijozlari qo‘ng‘iroqlarga javob bo‘lmagani sabab vaqt yo‘qotadi. "
        "“AgroKo‘mak” loyihasi klinika qo‘ng‘iroqlarini avtomatlashtiradi. "
        "“AgroKo‘mak” loyihasi Test University tomonidan ishlab chiqildi."
    )
    analysis = sample_analysis(article)
    pipeline = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer())
    result = pipeline.run()
    assert result["counts"]["new_projects"] == 1
    with factory() as session:
        project = session.scalar(select(Project))
        assert project.problem_gate_status == "PASS"
        assert project.opportunity_grade == "PENDING"
        assert project.problem_statement in article.text
        assert session.scalar(select(ProjectProblemLink))
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/problems").json()["total"] == 1
        detail = client.get("/api/projects/" + project.id).json()
        assert detail["related_problems"]
        assert detail["content"]["facts"][0]["quote"] == analysis.facts[0].quote


def test_pipeline_classifies_standalone_problem_without_product(settings, factory):
    from backend.app.pipeline import Pipeline
    from tests.conftest import FakeDiscovery, FakeAnalyzer

    article = sample_article()
    article.title = "Klinikalarda qo‘ng‘iroq muammosi"
    article.text = "Klinika mijozlari muntazam javobsiz qo‘ng‘iroqlar sabab vaqt yo‘qotadi."
    result = Pipeline(settings, factory, FakeDiscovery([article]), FakeAnalyzer()).run()
    assert result["counts"]["problems"] == 1
    with factory() as session:
        assert session.get(Candidate, article.url).status == "problem"
        assert session.scalar(select(Problem)).title_uz.startswith("Klinika")
