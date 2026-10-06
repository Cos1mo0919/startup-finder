import json
from typing import Protocol
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel
from ..dates import priority
from ..network import FetchError, safe_url
from ..schemas import SourceKind
from .parsers import parse_article, parse_feed


class SourceConfig(BaseModel):
    name: str
    url: str
    kind: SourceKind = "unknown"
    enabled: bool = True


def load_sources(path):
    return [SourceConfig.model_validate(s) for s in json.loads(path.read_text()) if s.get("enabled", True)]


class SearchAdapter(Protocol):
    def search(self, query: str, freshness: str = "pm") -> list[str]: ...


class NoSearch:
    def search(self, query, freshness="pm"):
        return []


class BraveSearch:
    def __init__(self, key):
        self.key = key

    def search(self, query, freshness="pm"):
        try:
            with httpx.Client(timeout=20) as client:
                r = client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": self.key, "Accept": "application/json"},
                    params={"q": query, "count": 10, "freshness": freshness},
                )
                r.raise_for_status()
                payload = r.json()
            return [safe_url(item["url"]) for item in payload.get("web", {}).get("results", [])]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise FetchError("search_unavailable") from exc


class Discovery:
    def __init__(self, settings, web, search=None):
        self.settings, self.web = settings, web
        self.sources = load_sources(settings.sources_file)
        self.search = search or (
            BraveSearch(settings.search_api_key.get_secret_value())
            if settings.search_api_key.get_secret_value()
            else NoSearch()
        )

    def source_metadata(self, url):
        host = urlsplit(url).hostname
        for source in self.sources:
            if urlsplit(source.url).hostname == host:
                return source.name, source.kind
        return host, "unknown"

    def article(self, url, feed_date=None):
        raw, final_url = self.web.get(url)
        name, kind = self.source_metadata(final_url)
        return parse_article(raw, final_url, name, kind, feed_date)

    def discover(self, now, archive=False):
        links, errors, checked = [], [], 0
        for source in self.sources:
            checked += 1
            try:
                raw, _ = self.web.get(source.url)
                links.extend(parse_feed(raw))
            except FetchError as exc:
                errors.append({"source": source.name, "code": str(exc)})
        if not isinstance(self.search, NoSearch):
            queries = [
                "O‘zbekiston startap loyiha prototip tanlov universitet",
                "Узбекистан стартап проект хакатон разработка инвестиции",
                "Uzbekistan startup research agriculture healthcare energy demo day",
            ]
            for freshness in ["2022-01-01to" + now.strftime("%Y-%m-%d")] if archive else ["pd", "pw", "pm"]:
                for query in queries:
                    checked += 1
                    try:
                        links.extend(
                            {"url": u, "published_at": None} for u in self.search.search(query, freshness)
                        )
                    except FetchError as exc:
                        errors.append({"source": "Brave Search", "code": str(exc)})
                        break
                if errors and errors[-1]["source"] == "Brave Search":
                    break
        links.sort(key=lambda item: priority(item.get("published_at"), now))
        unique = list({item["url"]: item for item in reversed(links)}.values())[::-1]
        return unique[: self.settings.max_candidates], errors, checked

    def corroborate(self, name, original_url):
        return [
            u
            for u in self.search.search(f'"{name}" Uzbekistan O‘zbekiston', "2022-01-01to2030-01-01")
            if u != original_url
        ][:3]
