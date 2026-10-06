import re
from itertools import zip_longest
from typing import Protocol
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from ..dates import priority
from ..db import Event, RegistrySource
from ..events import event_queries, followup_due
from ..network import FetchError, safe_url, canonical_url
from ..registry import due, record_check, seed_registry, source_for_url
from .parsers import parse_article, parse_feed


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
    def __init__(self, settings, web, search=None, factory=None):
        self.settings, self.web, self.factory = settings, web, factory
        self.force = False
        if factory:
            seed_registry(factory, settings.sources_file)
            with factory() as session:
                self.sources = list(session.scalars(select(RegistrySource)))
            if settings.trusted_egress_proxy:
                web.proxy_hosts.update(urlsplit(s.url).hostname for s in self.sources if s.enabled)
        else:
            self.sources = []
        self.search = search or (
            BraveSearch(settings.search_api_key.get_secret_value())
            if settings.search_api_key.get_secret_value()
            else NoSearch()
        )

    def article(self, url, feed_date=None):
        raw, final_url = self.web.get(url)
        with self.factory() as session:
            source = source_for_url(session, final_url)
            name, kind = (
                (source.name, source.trust_kind) if source else (urlsplit(final_url).hostname, "unknown")
            )
            result = parse_article(raw, final_url, name, kind, feed_date)
            result.source_id = source.id if source else None
            return result

    def page_links(self, url, pattern=""):
        raw, final = self.web.get(url)
        soup = BeautifulSoup(raw, "html.parser")
        links = []
        for anchor in soup.select("a[href]")[:400]:
            try:
                link = canonical_url(urljoin(final, anchor["href"]))
                if urlsplit(link).hostname != urlsplit(final).hostname or link == canonical_url(final):
                    continue
                if pattern and not re.search(pattern, link):
                    continue
                links.append({"url": link, "published_at": None})
            except (FetchError, ValueError):
                continue
        return list({item["url"]: item for item in links}.values())[:40]

    def collect(self, source, now, archive):
        method = source.collection_method
        if method == "RSS":
            raw, _ = self.web.get(source.url)
            return parse_feed(raw)
        if method == "direct_page":
            if source.options.get("single_article"):
                self.web.get(source.url)
                return [{"url": source.url, "published_at": None}]
            if not source.options.get("link_pattern"):
                raise FetchError("source_requires_configuration")
            return self.page_links(source.url, source.options["link_pattern"])
        if method == "search":
            if isinstance(self.search, NoSearch):
                raise FetchError("requires_api_key")
            query = source.options.get("query", "")
            if not query:
                raise FetchError("source_requires_configuration")
            regions = source.options.get("regions", []) or ["Uzbekistan"]
            # Rotate a persistent hourly calendar, covering all configured regions without an API burst.
            slot = int(now.timestamp() // (source.check_frequency * 60)) % len(regions)
            query = query.replace("{region}", regions[slot])
            freshness = "2022-01-01to" + now.strftime("%Y-%m-%d") if archive else "pm"
            return [{"url": u, "published_at": None} for u in self.search.search(query, freshness)]
        raise FetchError("source_requires_configuration")

    def discover(self, now, archive=False):
        batches, errors, checked = [], [], 0
        with self.factory() as session:
            sources = list(
                session.scalars(
                    select(RegistrySource).order_by(RegistrySource.priority.desc(), RegistrySource.id)
                )
            )
        for source in sources:
            if not due(source, now, self.force):
                continue
            checked += 1
            try:
                links = self.collect(source, now, archive)
                for item in links:
                    item["source_id"] = source.id
                links.sort(key=lambda item: priority(item.get("published_at"), now))
                batches.append(links)
                record_check(self.factory, source.id, now, len(links))
            except FetchError as exc:
                record_check(self.factory, source.id, now, error=str(exc))
                errors.append({"source": source.name, "code": str(exc)})
        # Fair per-source budget: local sources cannot be crowded out by a large news RSS.
        links = []
        seen = set()
        for group in zip_longest(*batches):
            for item in group:
                if item and canonical_url(item["url"]) not in seen:
                    seen.add(canonical_url(item["url"]))
                    links.append(item)
        return links[: self.settings.max_candidates], errors, checked

    def follow_events(self, now):
        with self.factory() as session:
            events = [
                e
                for e in session.scalars(select(Event).order_by(Event.discovered_at.desc()))
                if followup_due(e, now)
            ]
        links, errors = [], []
        for event in events[: self.settings.max_event_followups]:
            error = ""
            try:
                found = []
                if not isinstance(self.search, NoSearch):
                    for query in event_queries(event):
                        found.extend(
                            {"url": u, "published_at": None} for u in self.search.search(query, "pm")
                        )
                elif event.official_url:
                    found = self.page_links(
                        event.official_url,
                        "winner|project|loyiha|g.olib|demo|startup|team|participant|natija",
                    )
                else:
                    raise FetchError("event_requires_search_key")
                links.extend(
                    {**item, "event_id": event.id, "source_id": event.source_id} for item in found[:10]
                )
            except FetchError as exc:
                error = str(exc)
                errors.append({"source": event.name, "code": error})
            with self.factory.begin() as session:
                stored = session.get(Event, event.id)
                stored.last_checked_at = now
                stored.last_error = error
        return links, errors

    def corroborate(self, name, original_url):
        return [u for u in self.search.search(f'"{name}" Uzbekistan O‘zbekiston', "pm") if u != original_url][
            :3
        ]
