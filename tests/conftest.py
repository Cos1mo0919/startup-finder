from tests.admin_key import ADMIN_KEY
from datetime import timedelta
from types import SimpleNamespace

import pytest
from backend.app.config import Settings
from backend.app.db import make_db, now_utc
from backend.app.schemas import Analysis, Article, Evidence, Fact


@pytest.fixture(autouse=True)
def isolated_memory_guard(monkeypatch):
    """The daily memory guard reads the *peak* RSS of the whole process. In
    production each run is a fresh process; in pytest hundreds of tests share
    one, so the peak would eventually trip the guard in unrelated tests. Report
    a small fixed peak unless a test sets its own (see test_memory_guard_*)."""
    fake = SimpleNamespace(ru_maxrss=64 * 1024)  # 64 MiB, in KiB like Linux
    monkeypatch.setattr("backend.app.free_budget.process_resource",
                        SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _who: fake))
    return fake


@pytest.fixture
def settings(tmp_path):
    sources = tmp_path / "sources.json"
    sources.write_text("[]")
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/test.sqlite3",
        sources_file=sources,
        scheduler_enabled=False,
        ai_api_key="",
        openai_api_key="",
        gemini_api_key="",
        openrouter_api_key="",
        groq_api_key="",
        search_api_key="",
        admin_api_key=ADMIN_KEY,
    )


@pytest.fixture
def factory(settings):
    engine, factory = make_db(settings.database_url)
    yield factory
    engine.dispose()


def sample_article(name="AgroKo‘mak", url="https://news.example/article", publisher="Sinov nashri"):
    quote = (f"O‘zbekiston uchun “{name}” loyihasi Test University tomonidan ishlab chiqildi. "
             f"Talabalar uchun arizalarni qo‘lda yuritish bilan vaqt sarflanadi. "
             f"{name} tizimi bu ishni avtomatlashtiradi va talabalar uchun taqdim etildi.")
    return Article(
        url=url,
        publisher=publisher,
        title=f"“{name}” loyihasi",
        text=quote,
        published_at=now_utc() - timedelta(hours=2),
        kind="news",
        language="uz",
    )


def sample_analysis(article=None, name="AgroKo‘mak"):
    article = article or sample_article(name)
    return Analysis(
        is_project=True,
        uzbekistan_related=True,
        name=name,
        creator="Test University",
        summary_uz=article.text,
        what_uz=article.text,
        category="agriculture",
        audience="individual",
        audience_groups=["Talabalar"],
        facts=[Fact(text_uz=article.text, quote=article.text, source_url=article.url)],
        evidence=Evidence(practical="prototype", practical_fact=0, problem="stated", problem_fact=0),
        ai_analysis_uz="Ushbu loyiha talabalar uchun foydali bo‘lishi mumkin. Qo‘shimcha dalillar kerak.",
    )


class FakeDiscovery:
    def __init__(self, articles):
        self.articles = articles

    def discover(self, now, archive=False):
        return [{"url": a.url} for a in self.articles], [], 1

    def article(self, url, feed_date=None):
        return next(a for a in self.articles if a.url == url)

    def corroborate(self, name, url, country="Uzbekistan"):
        return []


class FakeAnalyzer:
    def analyze(self, articles):
        return sample_analysis(articles[0])


@pytest.fixture
def offline_daily_preflight(monkeypatch):
    """Injected offline classifiers stand in for configured providers in component tests.

    Credential/preflight behavior is tested separately without this fixture.
    No real key or external provider call is introduced into these tests.
    """
    monkeypatch.setattr("backend.app.free_daily.llm_preflight", lambda settings: True)


def pytest_runtest_logreport(report):
    """On GitHub Actions, surface failing tests as check annotations."""
    import os
    import sys
    if report.failed and os.environ.get("GITHUB_ACTIONS") == "true":
        path, line, _ = report.location
        message = str(report.longrepr).strip().splitlines()[-1][:500].replace("%", "%25")
        sys.__stdout__.write(f"::error file={path},line={(line or 0) + 1}::{report.nodeid}: {message}\n")
        sys.__stdout__.flush()
