import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from backend.app.collectors.archive import archive_links
from backend.app.collectors.sources import Discovery


def test_show_hn_archive_uses_all_months_and_preserves_submission_url():
    requested = []

    class Web:
        def get(self, url):
            requested.append(url)
            filters = parse_qs(urlsplit(url).query)["numericFilters"][0]
            timestamp = int(filters.split(",")[0].split(">=")[1])
            payload = {"nbPages": 2, "hits": [
                {"title": "Show HN: Useful project", "url": f"https://example.org/product-{timestamp}",
                 "objectID": str(timestamp), "created_at_i": timestamp},
                {"title": "Ordinary news", "url": "https://example.org/news",
                 "objectID": "2", "created_at_i": timestamp},
            ]}
            return json.dumps(payload).encode(), url

    discovery = SimpleNamespace(web=Web(), settings=SimpleNamespace(archive_pages=10), archive_coverage=[])
    source = SimpleNamespace(id="show-hn-rss", options={"archive": {"hn_algolia": True}})
    links = archive_links(discovery, source, (date(2026, 1, 1), date(2026, 10, 10)))
    assert len(requested) == len(links) == 10
    final_upper = max(int(parse_qs(urlsplit(url).query)["numericFilters"][0].split("<=")[1])
                      for url in requested)
    assert datetime.fromtimestamp(final_upper, timezone.utc).isoformat() == "2026-10-10T18:59:59+00:00"
    assert all(link["discovery_url"].startswith("https://news.ycombinator.com/item?id=") for link in links)
    assert all(link["title"].startswith("Show HN:") for link in links)
    coverage = discovery.archive_coverage[0]
    assert coverage["date_slices"] == 10 and coverage["pages_not_scanned_estimate"] == 10
    assert coverage["bounded"] is True


def test_show_hn_archive_works_with_existing_registry_options(monkeypatch):
    from backend.app.collectors import sources

    calls = []
    monkeypatch.setattr(sources, "show_hn_archive_links", lambda *args: calls.append(args) or [])
    discovery = Discovery.__new__(Discovery)
    discovery.window = (date(2026, 1, 1), date(2026, 10, 10))
    discovery.seed_configs = {"show-hn-rss": SimpleNamespace(options={"archive": {"hn_algolia": True}})}
    source = SimpleNamespace(id="show-hn-rss", collection_method="RSS", options={})
    assert discovery.collect(source, None, True) == []
    assert len(calls) == 1
