"""Bounded, robots-aware public archive traversal. Dates here select URLs only."""

import re
import json
from math import ceil
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET
from ..network import canonical_url, FetchError


def url_day(url):
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url)
    try:
        return date(*map(int, m.groups())) if m else None
    except ValueError:
        return None


def archive_links(discovery, source, window):
    if getattr(source, "collection_method", "") == "github_search":
        # Search repository creation dates as discovery hints. The repository
        # creation date is not asserted as the product launch date.
        return discovery.github_search(source, window)
    config = source.options.get("archive", {})
    if config.get("hn_algolia"):
        return show_hn_archive_links(discovery, source, window)
    if not config:
        # The current listing is useful only if it actually links old material.
        return discovery.collect(source, discovery.clock, False)
    result = {}
    if config.get("sitemap_index"):
        return sitemap_links(discovery, source, window, config)
    template = config.get("page_url")
    if not template:
        return []
    maximum = min(config.get("max_pages", discovery.settings.archive_pages), discovery.settings.archive_pages)
    pages = []
    for page in range(1, maximum + 1):
        url = template.format(page=page, year=window[0].year)
        # Share listing pages across yearly runs; each article is still fetched/validated normally.
        key = canonical_url(url)
        if key not in discovery.archive_cache:
            discovery.archive_cache[key] = discovery.page_links(
                url, config.get("link_pattern", source.options.get("link_pattern", ""))
            )
        items = discovery.archive_cache[key]
        pages.append(url)
        dates = []
        for item in items:
            day = url_day(item["url"])
            if day:
                dates.append(day)
            if day and not window[0] <= day <= window[1]:
                continue
            if config.get("target_pattern") and not re.search(
                config["target_pattern"], item.get("title", "") + " " + item["url"], re.I
            ):
                continue
            result[canonical_url(item["url"])] = item
        if dates and max(dates) < window[0]:
            break
        if not items:
            break
    discovery.archive_coverage.append(
        {
            "source_id": source.id,
            "year": window[0].year,
            "pages": len(pages),
            "candidates": len(result),
            "page_limit": maximum,
        }
    )
    return list(result.values())


def show_hn_archive_links(discovery, source, window):
    """Spread a bounded Show HN search across every date in the requested range."""
    tashkent = ZoneInfo("Asia/Tashkent")
    page_budget = discovery.settings.archive_pages
    total_days = (window[1] - window[0]).days + 1
    days_per_slice = ceil(total_days / page_budget)
    slices = []
    cursor = window[0]
    while cursor <= window[1]:
        end = min(cursor + timedelta(days=days_per_slice - 1), window[1])
        slices.append((cursor, end))
        cursor = end + timedelta(days=1)
    links = {}
    pages_used = 0
    reported_hits = 0
    next_pages = [0] * len(slices)
    available_pages = [1] * len(slices)
    api_capped_slices = set()
    page_failures = 0
    while pages_used < page_budget and any(next_pages[i] < available_pages[i] for i in range(len(slices))):
        for index, (start, end) in enumerate(slices):
            if pages_used >= page_budget:
                break
            page = next_pages[index]
            if page >= available_pages[index]:
                continue
            start_ts = int(datetime.combine(start, time.min, tashkent).astimezone(timezone.utc).timestamp())
            end_ts = int(datetime.combine(end + timedelta(days=1), time.min, tashkent).astimezone(timezone.utc).timestamp()) - 1
            params = urlencode({"query": "Show HN", "tags": "show_hn", "hitsPerPage": 100,
                                "page": page, "numericFilters": f"created_at_i>={start_ts},created_at_i<={end_ts}"})
            pages_used += 1
            try:
                raw, _ = discovery.web.get("https://hn.algolia.com/api/v1/search_by_date?" + params)
                payload = json.loads(raw)
                hits = payload["hits"]
            except (FetchError, ValueError, KeyError, TypeError):
                page_failures += 1
                available_pages[index] = page
                continue
            available_pages[index] = payload.get("nbPages", 0)
            next_pages[index] += 1
            if payload.get("nbHits", 0) > available_pages[index] * 100:
                api_capped_slices.add(index)
            reported_hits += len(hits)
            for hit in hits:
                title = hit.get("title") or ""
                if not title.casefold().startswith("show hn:") or not hit.get("url"):
                    continue
                try:
                    link = canonical_url(hit["url"])
                    published_at = datetime.fromtimestamp(int(hit["created_at_i"]), timezone.utc)
                    if not start <= published_at.astimezone(tashkent).date() <= end:
                        continue
                except (FetchError, ValueError, KeyError, TypeError, OverflowError):
                    continue
                if link not in links or published_at < links[link]["published_at"]:
                    links[link] = {"url": link, "title": title, "published_at": published_at,
                                   "discovery_url": "https://news.ycombinator.com/item?id=" + str(hit["objectID"])}
    pages_not_scanned = sum(max(0, available_pages[i] - next_pages[i]) for i in range(len(slices)))
    discovery.archive_coverage.append({"source_id": source.id, "year": window[0].year,
        "date_slices": len(slices), "days_per_slice": days_per_slice,
        "pages": pages_used, "page_limit": page_budget,
        "api_hits_examined": reported_hits, "candidates": len(links),
        "pages_not_scanned_estimate": pages_not_scanned, "api_capped_slices": len(api_capped_slices),
        "page_failures": page_failures,
        "bounded": pages_not_scanned > 0 or bool(api_capped_slices) or page_failures > 0})
    return list(links.values())


def sitemap_links(discovery, source, window, config):
    index = config["sitemap_index"]
    if index not in discovery.archive_cache:
        raw, _ = discovery.web.get(index)
        discovery.archive_cache[index] = [
            n.text for n in parse_sitemap(raw).iter() if n.tag.endswith("}loc") or n.tag == "loc"
        ]
    maps = [
        u
        for u in discovery.archive_cache[index]
        if re.search(config["sitemap_pattern"].replace("{year}", str(window[0].year)), u)
    ]
    # Stratify across the whole year instead of exhausting January or December first.
    maps.sort()
    limit = min(len(maps), discovery.settings.archive_pages)
    selected = [maps[round(i * (len(maps) - 1) / max(1, limit - 1))] for i in range(limit)]
    links = {}
    for url in selected:
        if url not in discovery.archive_cache:
            raw, _ = discovery.web.get(url)
            discovery.archive_cache[url] = [
                n.text for n in parse_sitemap(raw).iter() if n.tag.endswith("}loc") or n.tag == "loc"
            ]
        for location in discovery.archive_cache[url]:
            day = url_day(location)
            if (
                day
                and window[0] <= day <= window[1]
                and re.search(config.get("target_pattern", "."), location, re.I)
            ):
                links[canonical_url(location)] = {"url": location, "published_at": None}
    discovery.archive_coverage.append(
        {
            "source_id": source.id,
            "year": window[0].year,
            "sitemaps_available": len(maps),
            "selected_sitemaps": selected,
            "pages": len(selected),
            "candidates": len(links),
            "page_limit": discovery.settings.archive_pages,
        }
    )
    return list(links.values())


def parse_sitemap(raw):
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise FetchError("invalid_sitemap") from exc
