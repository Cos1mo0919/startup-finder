import json
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
import feedparser
from ..dates import parse_date
from ..network import FetchError, safe_url
from ..schemas import Article

PARSER_VERSION = 2


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
        entries.append(
            {"url": url, "title": entry.get("title", ""), "published_at": parse_date(entry.get("published"))}
        )
    return entries


def parse_article(raw, url, publisher="", kind="unknown", feed_date=None):
    soup = BeautifulSoup(raw, "html.parser")
    title_meta = soup.find("meta", property="og:title")
    title = (
        title_meta.get("content", "")
        if title_meta
        else (soup.title.get_text(" ", strip=True) if soup.title else "")
    )
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
    if not published:
        stamp = soup.find("time", datetime=True)
        published = parse_date(stamp.get("datetime")) if stamp else feed_date
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
    language = soup.html.get("lang", "") if soup.html else ""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    body = (
        soup.select_one('[itemprop="articleBody"]')
        or soup.find("article")
        or soup.find("main")
        or soup.body
        or soup
    )
    text = " ".join(body.stripped_strings)[:24000]
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
        url=url,
        publisher=publisher or urlsplit(url).hostname,
        title=title[:500],
        text=text,
        published_at=published,
        image_url=image,
        kind=kind,
        language=language,
    )
