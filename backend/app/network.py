import ipaddress
import json
import os
import socket
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from protego import Protego
import httpx


class FetchError(Exception):
    pass


def safe_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise FetchError("invalid_url")
    try:
        p = urlsplit(url)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            raise FetchError("https_public_only")
        host = p.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise FetchError("private_host")
        try:
            if not ipaddress.ip_address(host).is_global:
                raise FetchError("private_address")
        except ValueError:
            pass
        return urlunsplit(("https", host, p.path or "/", p.query, ""))
    except ValueError as exc:
        raise FetchError("invalid_url") from exc


def public_dns(url, proxy_trusted_hosts=()):
    host = urlsplit(safe_url(url)).hostname
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        # In managed clouds DNS is performed by the egress proxy. Only explicitly
        # configured hosts may use that path; arbitrary discovered hosts fail closed.
        if host in proxy_trusted_hosts and os.environ.get("HTTPS_PROXY", "").startswith(
            ("http://", "https://")
        ):
            return False
        raise FetchError("dns_failed") from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise FetchError("private_address")


def canonical_url(url):
    p = urlsplit(safe_url(url))
    query = [
        (k, v)
        for k, v in parse_qsl(p.query)
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
    ]
    return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


class WebClient:
    def __init__(self, settings):
        self.settings = settings
        self.proxy_hosts = set()
        if settings.trusted_egress_proxy:
            self.proxy_hosts = {
                urlsplit(safe_url(s["url"])).hostname
                for s in json.loads(settings.sources_file.read_text())
                if s.get("enabled", True)
            }
        self.client = httpx.Client(
            timeout=settings.fetch_timeout, headers={"User-Agent": settings.user_agent}
        )
        self.proxy_dns_verified = set()
        self.robots = {}
        self.last_request = {}

    def close(self):
        self.client.close()

    def _fetch(self, url, robots=False):
        for _ in range(5):
            url = safe_url(url)
            host = urlsplit(url).netloc
            # Cache only the explicitly trusted proxy-DNS fallback for this client lifetime.
            # Locally resolved destinations still undergo IP validation on every request.
            if host not in self.proxy_dns_verified:
                if public_dns(url, self.proxy_hosts) is False and host in self.proxy_hosts:
                    self.proxy_dns_verified.add(host)
            wait = max(0, self.last_request.get(host, 0) + 1 - time.monotonic())
            if wait:
                time.sleep(wait)
            self.last_request[host] = time.monotonic()
            try:
                with self.client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        target = safe_url(urljoin(url, response.headers.get("location", "")))
                        if not robots:
                            self._check_robots(target)
                        url = target
                        continue
                    if robots and response.status_code == 404:
                        return b"", url
                    if response.status_code != 200:
                        raise FetchError(f"http_{response.status_code}")
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(t in content_type for t in ("text/", "xml", "html", "json")):
                        raise FetchError("unsupported_content_type")
                    data = bytearray()
                    for chunk in response.iter_bytes(chunk_size=16384):
                        data.extend(chunk)
                        if len(data) > self.settings.max_page_bytes:
                            raise FetchError("page_too_large")
                    return bytes(data), url
            except httpx.HTTPError as exc:
                raise FetchError("network_unavailable") from exc
        raise FetchError("too_many_redirects")

    def _check_robots(self, url):
        origin = "https://" + urlsplit(safe_url(url)).netloc
        if origin not in self.robots:
            raw, _ = self._fetch(origin + "/robots.txt", robots=True)
            parser = Protego.parse(raw.decode("utf-8", errors="replace"))
            self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(url, self.settings.user_agent):
            raise FetchError("robots_disallowed")
        delay = parser.crawl_delay(self.settings.user_agent) or parser.crawl_delay("*") or 1
        host = urlsplit(url).netloc
        wait = max(0, self.last_request.get(host, 0) + min(delay, 60) - time.monotonic())
        if delay > 60:
            raise FetchError("crawl_delay_too_long")
        if wait:
            time.sleep(wait)

    def get(self, url):
        self._check_robots(url)
        return self._fetch(url)
