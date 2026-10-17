import json
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
import feedparser
from ..dates import parse_date
from ..network import FetchError, safe_url
from ..schemas import Article

PARSER_VERSION = 4


def parse_feed(raw):
    parsed = feedparser.parse(raw)
    if parsed.bozo and not parsed.entries:
        raise FetchError("invalid_feed")
    entries = []
    for entry in parsed.entries[:200]:
        try:
            url = safe_url(entry.get("link", ""))
        except FetchError:
            continue
        item = {"url": url, "title": entry.get("title", ""), "published_at": parse_date(entry.get("published"))}
        # Show HN feeds link directly to the maker's site. Keep the submission
        # as discovery provenance without treating it as official evidence.
        comments = entry.get("comments", "")
        if isinstance(comments, str) and comments.startswith("https://news.ycombinator.com/item?id="):
            item["discovery_url"] = comments
        entries.append(item)
    return entries


def parse_article(*args, **kwargs):
    from ..telemetry import span
    with span("extraction"):
        return _parse_article(*args, **kwargs)


def _parse_article(raw, url, publisher="", kind="unknown", feed_date=None, options=None):
    options = options or {}
    soup = BeautifulSoup(raw, "html.parser")
    title_meta = soup.find("meta", property="og:title")
    title = (
        title_meta.get("content", "")
        if title_meta
        else (soup.title.get_text(" ", strip=True) if soup.title else "")
    )
    heading = soup.find("h1")
    if heading:
        heading_text = heading.get_text(" ", strip=True)
        if not title or (len(heading_text) > len(title) and heading_text.startswith(title)):
            title = heading_text
    published = None
    # Publication date only: modified timestamps must never make old articles look new.
    for attrs in [
        {"property": "article:published_time"},
        {"name": "datePublished"},
        {"itemprop": "datePublished"},
    ]:
        tag = soup.find("meta", attrs=attrs)
        if tag:
            published = parse_date(tag.get("content"))
            if published:
                break
    if not published:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                nodes = data if isinstance(data, list) else [data]
                for node in nodes:
                    if isinstance(node, dict):
                        for item in [node, *node.get("@graph", [])]:
                            if isinstance(item, dict) and item.get("datePublished"):
                                published = parse_date(item["datePublished"])
                                break
            except (ValueError, TypeError):
                continue
    if not published and not options.get("date_selector"):
        stamp = soup.find("time", datetime=True)
        published = parse_date(stamp.get("datetime")) if stamp else feed_date
    if not published and options.get("date_selector"):
        stamp = soup.select_one(options["date_selector"])
        if stamp:
            value = stamp.get("datetime") or stamp.get_text(" ", strip=True)
            match = re.search(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b", value)
            if match:
                published = parse_date(f"{match[3]}-{match[2]}-{match[1]}")
            else:
                months = {
                    "yanvar": 1,
                    "fevral": 2,
                    "mart": 3,
                    "aprel": 4,
                    "may": 5,
                    "iyun": 6,
                    "iyul": 7,
                    "avgust": 8,
                    "sentabr": 9,
                    "sentyabr": 9,
                    "oktabr": 10,
                    "oktyabr": 10,
                    "noyabr": 11,
                    "dekabr": 12,
                }
                match = re.search(r"(\d{1,2})[- ]([a-z]+),?\s+(20\d{2})", value.lower())
                if match and match[2] in months:
                    published = parse_date(f"{match[3]}-{months[match[2]]:02d}-{int(match[1]):02d}")
                elif re.fullmatch(r"20\d{2}-\d{2}-\d{2}(?:.*)", value):
                    published = parse_date(value)
    image = None
    image_meta = soup.find("meta", property="og:image")
    if image_meta:
        try:
            image = safe_url(urljoin(url, image_meta.get("content", "")))
            # Avoid unrelated third-party tracking URLs in source-provided metadata.
            if urlsplit(image).hostname != urlsplit(url).hostname:
                image = None
        except FetchError:
            pass
    from ..telemetry import record
    language = soup.html.get("lang", "") if soup.html else ""
    structured = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            nodes = json.loads(script.string or "")
            nodes = nodes if isinstance(nodes, list) else [nodes]
            for node in nodes:
                if isinstance(node, dict):
                    for item in [node, *node.get("@graph", [])]:
                        if isinstance(item, dict):
                            value = item.get("articleBody") or item.get("description")
                            if isinstance(value, str):
                                structured.append(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))
        except (ValueError, TypeError):
            pass
    metadata = [tag.get("content", "") for tag in soup.select('meta[property="og:description"], meta[name="description"]')]
    js_shell = bool(soup.find("script", src=True))
    paywall = bool(soup.select('[class*="paywall"], [id*="paywall"]'))
    selector_missing = bool(options.get("body_selector") and not soup.select_one(options["body_selector"]))
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    body = (
        (soup.select_one(options["body_selector"]) if options.get("body_selector") else None)
        or soup.select_one('[itemprop="articleBody"]')
        or soup.find("article")
        or soup.find("main")
        or soup.body
        or soup
    )
    for selector in options.get("exclude_selectors", []):
        for element in body.select(selector):
            element.decompose()
    text = " ".join(body.stripped_strings)[:24000]
    method = "configured_or_semantic_body"
    if selector_missing or len(text.split()) < 8:
        # Use dense prose blocks, not menus, for selector drift. Metadata is
        # source evidence only; it never bypasses classifier/publication gates.
        prose = max((tag.get_text(" ", strip=True) for tag in body.find_all(["article", "section", "div", "p"])
                     if len(tag.find_all("a")) <= 5), key=len, default="")
        choices = [("json_ld", value) for value in structured] + [("prose_fallback", prose)] + [("meta_description", value) for value in metadata]
        usable = [(name, value) for name, value in choices if len(value.split()) >= 8]
        if usable:
            method, text = max(usable, key=lambda item: len(item[1]))
            text = text[:24000]
        elif selector_missing or not text.strip() or ((paywall or js_shell) and len(text.split()) < 8):
            reason = "paywall_detected" if paywall else "js_shell" if js_shell and len(text.split()) < 8 else "selector_missing" if selector_missing else "empty_text"
            record("extraction", method="none", reason=reason, words=len(text.split()))
            raise FetchError("article_body_missing")
    record("extraction", method=method, words=len(text.split()), selector_missing=selector_missing, encoding_replacements=text.count("\ufffd"))
    # Preserve attributed hyperlinks for official/project/creator link extraction.
    links = []
    for anchor in body.find_all("a", href=True)[:50]:
        try:
            href = safe_url(urljoin(url, anchor["href"]))
            links.append(anchor.get_text(" ", strip=True)[:150] + ": " + href)
        except FetchError:
            continue
    if links:
        text += "\nHavolalar: " + " | ".join(links)[:4000]
    return Article(
        parser_version=PARSER_VERSION,
        url=url,
        publisher=publisher or urlsplit(url).hostname,
        title=title[:500],
        text=text,
        published_at=published,
        image_url=image,
        kind=kind,
        language=language,
    )
