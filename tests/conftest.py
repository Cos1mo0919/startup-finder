from datetime import timedelta
import pytest
from backend.app.config import Settings
from backend.app.db import make_db, now_utc
from backend.app.schemas import Analysis, Article, Evidence, Fact


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
        admin_api_key="test-admin-key",
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
