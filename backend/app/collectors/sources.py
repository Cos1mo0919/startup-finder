import json
import re
from itertools import zip_longest
from typing import Protocol
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from ..dates import priority
from ..queries import targeted_queries, freshness
from .archive import archive_links, show_hn_archive_links
from ..db import Event, RegistrySource, Candidate
from ..events import event_queries, followup_due
from ..network import FetchError, safe_url, canonical_url
from ..registry import due, record_check, seed_registry, source_for_url, load_sources
from .parsers import parse_article, parse_feed


def structured_project_fields(raw, options):
    """Extract only explicit page fields selected by a source-specific adapter."""
    soup = BeautifulSoup(raw, "html.parser")
    name_selector = options.get("project_name_selector")
    description_selector = options.get("project_description_selector")
    if name_selector and description_selector:
        name_node = soup.select_one(name_selector)
        description_node = soup.select_one(description_selector)
        return (name_node.get_text(" ", strip=True) if name_node else "",
                description_node.get_text(" ", strip=True) if description_node else "")
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.string or node.get_text())
            objects = payload if isinstance(payload, list) else payload.get("@graph", [payload])
            for item in objects:
                if isinstance(item, dict) and item.get("@type") in ("Product", "SoftwareApplication"):
                    return str(item.get("name") or ""), str(item.get("description") or "")
        except (ValueError, TypeError, AttributeError):
            continue
    return "", ""


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
            if source:
                result.adapter = source.id
                result.page_type = source.options.get("page_type", "news_article" if source.source_type == "news" else "")
                result.country_hint = source.country or ""
                result.structured_category = source.options.get("catalog_category", "")
                if result.page_type and result.page_type != "news_article":
                    result.project_name, result.project_description = structured_project_fields(raw, source.options)
            return result

    def page_links(self, url, pattern="", match_text=False, selector="a[href]"):
        raw, final = self.web.get(url)
        soup = BeautifulSoup(raw, "html.parser")
        links = []
        for anchor in soup.select(selector)[:2000]:
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
            if (source.id == "show-hn-rss" and seed and
                    seed.options.get("archive", {}).get("hn_algolia")):
                return show_hn_archive_links(self, source, self.window)
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
            if source.id == "show-hn-rss":
                # The feed's URL is the creator's site; retain the HN submission
                # separately as the discovery source, never as primary evidence.
                links = [item for item in links if item.get("title", "").startswith("Show HN:")]
                return links
            pattern = source.options.get("link_pattern")
            return [item for item in links if re.search(pattern, item["url"], re.I)] if pattern else links
        if method == "direct_page":
            if source.options.get("single_article"):
                self.web.get(source.url)
                return [{"url": source.url, "published_at": None}]
            if not source.options.get("link_pattern"):
                raise FetchError("source_requires_configuration")
            return self.page_links(source.url, source.options["link_pattern"],
                                   selector=source.options.get("link_selector", "a[href]"))
        if method == "github_search":
            return self.github_search(source)
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

    def github_search(self, source):
        """Use GitHub's public repository search with its own optional credential."""
        import httpx
        from urllib.parse import urlencode
        from ..network import public_dns

        queries = source.options.get("queries") or [
            "Uzbekistan startup in:name,description,readme",
            "Tashkent project in:name,description,readme",
            "startup launch in:name,description,readme",
        ]
        token = self.settings.github_token.get_secret_value()
        headers = {"User-Agent": self.settings.user_agent,
                   "Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        public_dns("https://api.github.com/")
        found = {}
        try:
            with httpx.Client(timeout=self.settings.fetch_timeout, headers=headers) as client:
                for query in queries[:3]:
                    url = "https://api.github.com/search/repositories?" + urlencode(
                        {"q": query, "sort": "updated", "order": "desc", "per_page": 30})
                    response = client.get(url)
                    if response.status_code in (403, 429):
                        raise FetchError("github_rate_limited")
                    if response.status_code != 200:
                        raise FetchError(f"http_{response.status_code}")
                    for item in response.json().get("items", []):
                        if item.get("html_url") and item.get("description"):
                            found[item["html_url"]] = {"url": item["html_url"],
                                "title": item.get("full_name", ""),
                                "description": item["description"][:500],
                                "published_at": None}
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise FetchError("github_network_unavailable") from exc
        return list(found.values())

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
                coverage = next((item for item in reversed(self.archive_coverage)
                                 if item.get("source_id") == source.id), {})
                if coverage.get("page_failures"):
                    errors.append({"source": source.name, "source_id": source.id,
                                   "stage": "archive", "code": "archive_pages_failed",
                                   "count": coverage["page_failures"]})
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

    def corroborate(self, name, original_url, country="Uzbekistan"):
        query = f'"{name}" Uzbekistan O‘zbekiston' if country == "Uzbekistan" else f'"{name}" startup product'
        return [u for u in self.search.search(query, "pm") if u != original_url][:3]

    def resolve_official(self, name, article):
        """Check a named project link in an article against the linked page."""
        links = article.text.split("\nHavolalar:", 1)
        if len(links) != 2:
            return None
        original_host = urlsplit(article.url).hostname
        for entry in links[1].split(" | ")[:30]:
            label, separator, candidate = entry.rpartition(": ")
            if not separator or not re.search(re.escape(name), label, re.I):
                continue
            try:
                candidate = safe_url(candidate.strip())
                if urlsplit(candidate).hostname == original_host:
                    continue
                raw, _ = self.web.get(candidate)
                soup = BeautifulSoup(raw, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                excerpt = " ".join(soup.stripped_strings)[:1500]
                if re.search(re.escape(name), title + " " + excerpt, re.I):
                    quote = title if re.search(re.escape(name), title, re.I) else excerpt[:500]
                    return candidate, quote
            except (FetchError, ValueError):
                continue
        return None


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
