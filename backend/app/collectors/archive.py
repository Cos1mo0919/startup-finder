"""Bounded, robots-aware public archive traversal. Dates here select URLs only."""

import re
from datetime import date
from xml.etree import ElementTree as ET
from ..network import canonical_url, FetchError


def url_day(url):
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url)
    try:
        return date(*map(int, m.groups())) if m else None
    except ValueError:
        return None


def archive_links(discovery, source, window):
    config = source.options.get("archive", {})
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
