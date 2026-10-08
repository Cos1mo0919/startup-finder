import re
from itertools import zip_longest
from typing import Protocol
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from ..dates import priority
from ..queries import targeted_queries, freshness
from .archive import archive_links
from ..db import Event, RegistrySource, Candidate
from ..events import event_queries, followup_due
from ..network import FetchError, safe_url, canonical_url
from ..registry import due, record_check, seed_registry, source_for_url, load_sources
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
        self.window = None
        self.clock = None
        self.archive_cache = {}
        self.archive_coverage = []
        self.allowed_source_ids = None
        self.seed_configs = {s.id: s for s in load_sources(settings.sources_file)}
        if factory:
            seed_registry(factory, settings.sources_file)
            with factory() as session:
                self.sources = list(session.scalars(select(RegistrySource)))
            if settings.trusted_egress_proxy:
                web.proxy_hosts.update(urlsplit(s.url).hostname for s in self.sources if s.enabled)
                for s in self.sources:
                    if s.enabled:
                        web.proxy_hosts.update(
                            urlsplit(safe_url("https://" + host + "/")).hostname
                            for host in s.options.get("article_hosts", [])
                        )
        else:
            self.sources = []
        self.search = search or (
            BraveSearch(settings.search_api_key.get_secret_value())
            if settings.search_api_key.get_secret_value()
            else NoSearch()
        )

    def article(self, url, feed_date=None):
        with self.factory() as session:
            configured = source_for_url(session, url)
            if (
                configured
                and configured.options.get("trailing_slash")
                and not urlsplit(url).path.endswith("/")
            ):
                from urllib.parse import urlunsplit

                parts = urlsplit(url)
                url = urlunsplit((parts.scheme, parts.netloc, parts.path + "/", parts.query, ""))
        raw, final_url = self.web.get(url)
        with self.factory() as session:
            source = source_for_url(session, final_url)
            name, kind = (
                (source.name, source.trust_kind) if source else (urlsplit(final_url).hostname, "unknown")
            )
            result = parse_article(raw, final_url, name, kind, feed_date, source.options if source else None)
            result.source_id = source.id if source else None
            return result

    def page_links(self, url, pattern="", match_text=False):
        raw, final = self.web.get(url)
        soup = BeautifulSoup(raw, "html.parser")
        links = []
        for anchor in soup.select("a[href]")[:2000]:
            try:
                link = safe_url(urljoin(final, anchor["href"].strip()))
                if urlsplit(link).hostname != urlsplit(final).hostname or canonical_url(
                    link
                ) == canonical_url(final):
                    continue
                if pattern and not re.search(
                    pattern, link + (" " + anchor.get_text(" ", strip=True) if match_text else ""), re.I
                ):
                    continue
                links.append(
                    {"url": link, "title": anchor.get_text(" ", strip=True)[:500], "published_at": None}
                )
            except (FetchError, ValueError):
                continue
        unique = {}
        for item in links:
            if item["url"] not in unique or len(item.get("title", "")) > len(
                unique[item["url"]].get("title", "")
            ):
                unique[item["url"]] = item
        return list(unique.values())[:80]

    def collect(self, source, now, archive):
        if archive and self.window and source.collection_method != "search":
            seed = self.seed_configs.get(source.id)
            if (
                seed
                and seed.options.get("archive")
                and not source.options.get("archive")
                and seed.url == canonical_url(source.url)
                and seed.collection_method == source.collection_method
            ):
                raise FetchError("archive_configuration_missing")
            return archive_links(self, source, self.window)
        method = source.collection_method
        if method == "RSS":
            raw, _ = self.web.get(source.url)
            links = parse_feed(raw)
            pattern = source.options.get("link_pattern")
            return [item for item in links if re.search(pattern, item["url"], re.I)] if pattern else links
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
            regions = source.options.get("regions", []) or ["Uzbekistan"]
            slot = int(now.timestamp() // (source.check_frequency * 60))
            region = regions[slot % len(regions)]
            year = self.window[0].year if self.window else None
            queries = targeted_queries(region, year)
            scoped = source.options.get("query", "").replace("{region}", region)
            if scoped:
                queries.insert(0, scoped + (f" {year}" if year else ""))
            budget = self.settings.search_queries_per_source
            chosen = queries if archive else [queries[(slot + i) % len(queries)] for i in range(budget)]
            found = []
            for query in chosen:
                found.extend(
                    {"url": u, "published_at": None, "query": query}
                    for u in self.search.search(query, freshness(self.window) if self.window else "pm")
                )
            return list({i["url"]: i for i in found}.values())

        raise FetchError("source_requires_configuration")

    def discover(self, now, archive=False):
        self.clock = now
        self.archive_coverage = []
        batches, errors, checked = [], [], 0
        with self.factory() as session:
            sources = list(
                session.scalars(
                    select(RegistrySource).order_by(RegistrySource.priority.desc(), RegistrySource.id)
                )
            )
        for source in sources:
            if self.allowed_source_ids is not None and source.id not in self.allowed_source_ids:
                continue
            if not due(source, now, self.force or bool(self.window)):
                continue
            checked += 1
            try:
                links = self.collect(source, now, archive)
                for item in links:
                    item["source_id"] = source.id
                    item["origin"] = source_origin(source)
                links.sort(key=lambda item: priority(item.get("published_at"), now))
                batches.append(links)
                record_check(self.factory, source.id, now, len(links))
            except FetchError as exc:
                record_check(self.factory, source.id, now, error=str(exc))
                errors.append(
                    {"source": source.name, "source_id": source.id, "stage": "source", "code": str(exc)}
                )
            except (ValueError, TypeError, re.error):
                record_check(self.factory, source.id, now, error="source_collection_invalid")
                errors.append(
                    {
                        "source": source.name,
                        "source_id": source.id,
                        "stage": "source",
                        "code": "source_collection_invalid",
                    }
                )
        # Fair per-source budget: local sources cannot be crowded out by a large news RSS.
        links = []
        seen = set()
        for group in zip_longest(*batches):
            for item in group:
                if item and canonical_url(item["url"]) not in seen:
                    seen.add(canonical_url(item["url"]))
                    links.append(item)
        return links, errors, checked

    def follow_events(self, now):
        with self.factory() as session:
            rejected_urls = set(session.scalars(select(Candidate.url).where(Candidate.status == "rejected")))
            events = [
                e
                for e in session.scalars(select(Event).order_by(Event.discovered_at.desc()))
                if e.source_url not in rejected_urls
                and (followup_due(e, now) or (self.force and e.status != "closed"))
            ]
        links, errors = [], []
        for event in events[: self.settings.max_event_followups]:
            error = ""
            try:
                found = []
                if not isinstance(self.search, NoSearch):
                    for query in event_queries(event, self.window):
                        found.extend(
                            {"url": u, "published_at": None}
                            for u in self.search.search(
                                query, freshness(self.window) if self.window else "pm"
                            )
                        )
                elif event.official_url or event.source_url:
                    found = self.page_links(
                        event.official_url or event.source_url,
                        "winner|project|loyiha|g.olib|demo|startup|startap|team|participant|natija|final|победител|участник",
                        match_text=True,
                    )
                    # Follow index/finalist pages, not arbitrary news links.
                    index_pattern = re.compile(r"winner|g.olib|final|participant|ishtirok|natija|победител|участник", re.I)
                    for item in [x for x in found if index_pattern.search(x["url"] + " " + x.get("title", ""))][:2]:
                        try:
                            found.extend(
                                self.page_links(
                                    item["url"],
                                    "winner|project|loyiha|team|demo|g.olib|participant",
                                    match_text=True,
                                )[:5]
                            )
                        except FetchError as exc:
                            errors.append({"source": item["url"], "stage": "event", "code": str(exc)})
                    found = list({canonical_url(item["url"]): item for item in found}.values())
                else:
                    raise FetchError("event_source_missing")
                links.extend(
                    {**item, "event_id": event.id, "source_id": event.source_id, "origin": "event_discovery"}
                    for item in found[:10]
                )
            except FetchError as exc:
                error = str(exc)
                errors.append({"source": event.name, "stage": "event", "code": error})
            with self.factory.begin() as session:
                stored = session.get(Event, event.id)
                stored.last_checked_at = now
                stored.last_error = error
        return links, errors

    def corroborate(self, name, original_url):
        return [u for u in self.search.search(f'"{name}" Uzbekistan O‘zbekiston', "pm") if u != original_url][
            :3
        ]


def source_origin(source):
    if source.collection_method == "search":
        return "web_search"
    if source.source_type == "university":
        return "university"
    if "it-park.uz" in source.url:
        return "it_park"
    if source.source_type == "hackathon":
        return "hackathon"
    if source.source_type == "accelerator":
        return "accelerator"
    if "uzhunt" in source.url:
        return "uzhunt"
    if source.collection_method == "RSS":
        return "rss"
    if source.source_type == "event":
        return "event_source"
    return "other"
