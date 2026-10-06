import json
import httpx
import pytest
from backend.app.analysis import AnalysisError, OpenAIAnalyzer, validate_analysis
from backend.app.collectors.parsers import parse_article, parse_feed
from backend.app.network import FetchError, WebClient, canonical_url, public_dns, safe_url
from tests.conftest import sample_analysis, sample_article


def test_rss_and_html_dates_images_and_scripts():
    raw = b'<rss version="2.0"><channel><item><title>Project</title><link>https://example.uz/p</link><pubDate>Tue, 06 Oct 2026 09:00:00 GMT</pubDate></item></channel></rss>'
    entries = parse_feed(raw)
    assert len(entries) == 1
    html = b"""<html lang="uz"><head><meta property="article:published_time" content="2021-01-01T00:00:00Z"><meta property="article:modified_time" content="2026-10-06T00:00:00Z"><meta property="og:image" content="/real.jpg"></head><body><nav>noise</nav><article>Actual project<script>bad()</script></article></body></html>"""
    a = parse_article(html, entries[0]["url"], feed_date=entries[0]["published_at"])
    assert a.published_at.year == 2021
    assert a.text == "Actual project"
    assert a.image_url == "https://example.uz/real.jpg"


def test_jsonld_publication_and_no_invented_date():
    html = b'<script type="application/ld+json">{"@graph":[{"datePublished":"2024-03-01T12:00:00Z"}]}</script><article>Text</article>'
    assert parse_article(html, "https://example.uz/a").published_at.year == 2024
    assert parse_article(b"<article>Text</article>", "https://example.uz/a").published_at is None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://localhost/x",
        "https://127.0.0.1",
        "https://[::1]",
        "https://user:password@example.com",
        "https://example.com:8080",
        "file:///etc/passwd",
        "https://169.254.169.254/latest",
    ],
)
def test_unsafe_urls_rejected(url):
    with pytest.raises(FetchError):
        safe_url(url)


def test_dns_private_address_blocked(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.2", 443))])
    with pytest.raises(FetchError, match="private_address"):
        public_dns("https://example.com")


def test_canonicalization_removes_tracking_not_identity():
    assert canonical_url("https://Example.com/p/?utm_source=x&id=4#here") == "https://example.com/p?id=4"


def test_quote_and_identity_hallucinations_rejected():
    a = sample_article()
    analysis = sample_analysis(a)
    analysis.facts[0].quote = "This quote does not exist."
    with pytest.raises(AnalysisError, match="unsupported_quote"):
        validate_analysis(analysis, [a])
    analysis = sample_analysis(a)
    analysis.creator = "Invented Person"
    with pytest.raises(AnalysisError, match="unsupported_identity"):
        validate_analysis(analysis, [a])


def test_translation_and_no_fabricated_links():
    a = sample_article()
    analysis = sample_analysis(a)
    analysis.main_url = "https://invented.example/"
    result = validate_analysis(analysis, [a])
    assert result.main_url is None
    analysis.summary_uz = "This project is useful for students and businesses."
    with pytest.raises(AnalysisError, match="translation_not_uzbek"):
        validate_analysis(analysis, [a])


def test_ai_adapter_mock_preserves_proper_names(settings, monkeypatch):
    a = sample_article()
    analysis = sample_analysis(a)
    settings.ai_api_key = "test-only"
    # SecretStr is provided at construction in production.
    from pydantic import SecretStr

    settings.ai_api_key = SecretStr("test-only")

    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_object"
        assert "UNTRUSTED DATA" in body["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": analysis.model_dump_json()}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("backend.app.analysis.public_dns", lambda u, *args: None)
    monkeypatch.setattr("backend.app.analysis.httpx.Client", lambda **kwargs: client)
    result = OpenAIAnalyzer(settings).analyze([a])
    assert result.name == "AgroKo‘mak"
    assert result.facts[0].source_url == a.url


def test_robots_and_size_limit(settings, monkeypatch):
    settings.max_page_bytes = 1000
    monkeypatch.setattr("backend.app.network.public_dns", lambda u, *args: None)
    monkeypatch.setattr("backend.app.network.time.sleep", lambda n: None)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, content=b"x" * 1001, headers={"content-type": "text/html"})

    web = WebClient(settings)
    web.client.close()
    web.client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError, match="robots_disallowed"):
        web.get("https://example.com/private")
    with pytest.raises(FetchError, match="page_too_large"):
        web.get("https://example.com/public")
    web.close()


def test_redirect_to_private_host_rejected(settings, monkeypatch):
    monkeypatch.setattr("backend.app.network.public_dns", lambda u, *args: None)
    monkeypatch.setattr("backend.app.network.time.sleep", lambda n: None)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "https://127.0.0.1/secret"})

    web = WebClient(settings)
    web.client.close()
    web.client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError):
        web.get("https://example.com/a")
    web.close()


def test_article_body_excludes_other_news_and_keeps_project_links():
    html = b"""<body><div itemprop="articleBody"><p>Real article text.</p><a href="https://project.uz/">Project</a></div><div>Unrelated Uzbekistan startup grant headlines</div></body>"""
    article = parse_article(html, "https://example.uz/a")
    assert "Unrelated" not in article.text
    assert "https://project.uz/" in article.text


def test_proxy_dns_is_explicit_and_host_scoped(monkeypatch):
    import socket

    def unavailable(*args, **kwargs):
        raise socket.gaierror(-3, "unavailable")

    monkeypatch.setattr("socket.getaddrinfo", unavailable)
    monkeypatch.setenv("HTTPS_PROXY", "http://managed-proxy.example:8080")
    public_dns("https://trusted.example/a", {"trusted.example"})
    with pytest.raises(FetchError, match="dns_failed"):
        public_dns("https://untrusted.example/a", {"trusted.example"})
    with pytest.raises(FetchError, match="dns_failed"):
        public_dns("https://trusted.example/a")


def test_robots_wildcards_are_respected(settings, monkeypatch):
    monkeypatch.setattr("backend.app.network.public_dns", lambda *a: None)
    monkeypatch.setattr("backend.app.network.time.sleep", lambda n: None)

    def handler(request):
        return httpx.Response(200, text="User-agent: *\nDisallow: /*?secret=*")

    web = WebClient(settings)
    web.client.close()
    web.client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError, match="robots_disallowed"):
        web.get("https://example.com/page?secret=1")
    web.close()


def test_brave_search_adapter_uses_official_api_and_freshness(monkeypatch):
    from backend.app.collectors.sources import BraveSearch

    def handler(request):
        assert request.url.host == "api.search.brave.com"
        assert request.url.params["freshness"] == "pd"
        assert request.headers["X-Subscription-Token"] == "test-only"
        return httpx.Response(200, json={"web": {"results": [{"url": "https://example.uz/project"}]}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("backend.app.collectors.sources.httpx.Client", lambda **kwargs: client)
    assert BraveSearch("test-only").search("Uzbekistan project", "pd") == ["https://example.uz/project"]


def test_foreign_source_translated_to_uzbek_keeps_original_names(settings, monkeypatch):
    from pydantic import SecretStr

    a = sample_article()
    a.title = "AgroKo‘mak launched in Uzbekistan"
    a.text = "The university developed AgroKo‘mak, a prototype launched in Uzbekistan for students."
    a.language = "en"
    result = sample_analysis()
    result.creator = "university"
    result.facts[0].quote = a.text
    result.facts[0].source_url = a.url
    settings.ai_api_key = SecretStr("test-only")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": result.model_dump_json()}}]}
            )
        )
    )
    monkeypatch.setattr("backend.app.analysis.public_dns", lambda *args: None)
    monkeypatch.setattr("backend.app.analysis.httpx.Client", lambda **kwargs: client)
    translated = OpenAIAnalyzer(settings).analyze([a])
    assert translated.name == "AgroKo‘mak"
    assert translated.creator == "university"
    assert "O‘zbekiston" in translated.summary_uz
    assert translated.facts[0].quote == a.text
