"""Exclusive catalog sections based on provenance; never infer a country fact."""

from urllib.parse import urlsplit


LOCAL_SOURCE_IDS = {"uzhunt", "spot-uz", "spot-ru", "spot-startups", "itpark", "ictweek"}
GLOBAL_SOURCE_IDS = {
    "show-hn-rss", "show-hn", "product-hunt", "yc-companies", "betalist",
    "indie-hackers", "github-trending", "huggingface-spaces", "astana-hub",
    "digital-business-kz", "kursiv-kz", "the-tech-kz", "tech-garden-kz",
    "reddit-startups", "g2", "capterra", "arxiv-ai", "sifted",
    "eu-startups", "tech-in-asia", "techcabal",
}
LOCAL_HOSTS = {"uzhunt.uz", "spot.uz", "it-park.uz", "ictweek.uz"}
GLOBAL_HOSTS = {"news.ycombinator.com", "hnrss.org", "producthunt.com", "ycombinator.com"}
LOCAL_SOURCE_IDS.update({"startupbase", "startup-ilmiy", "loyiha-ilmiy", "debocha"})
GLOBAL_SOURCE_IDS.update({"microlaunch", "uneed"})
LOCAL_HOSTS.update({"startupbase.uz", "stanbase.uz", "startup.ilmiy.uz", "loyiha.ilmiy.uz", "debocha.uz"})
GLOBAL_HOSTS.update({"betalist.com", "indiehackers.com", "microlaunch.net", "uneed.best"})


def _host(url):
    return ((urlsplit(url).hostname or "").lower().removeprefix("www.") if url else "")


def project_scope(project) -> str:
    """Return one catalog section; unknown provenance is not a country fact."""
    override = getattr(project, "catalog_section_override", "") or ""
    if override in {"GitHub", "Uzbekistan", "Global", "Boshqa"}:
        return override
    sources = project.sources or []
    urls = [project.discovery_source_url, *(source.url for source in sources)]
    hosts = {_host(url) for url in urls}
    if any(host == "github.com" or host.endswith(".github.com") for host in hosts):
        return "GitHub"
    ids = {source.source_id for source in sources}
    if ids & LOCAL_SOURCE_IDS or any(host in LOCAL_HOSTS or host.endswith(".uz") for host in hosts):
        return "Uzbekistan"
    if ids & GLOBAL_SOURCE_IDS or any(host in GLOBAL_HOSTS for host in hosts):
        return "Global"
    country = (project.country or "").strip().casefold()
    if country in {"uzbekistan", "o‘zbekiston", "узбекистан"}:
        return "Uzbekistan"
    return "Global" if country else "Boshqa"


def section_reason(project) -> str:
    if project_scope(project) != "Boshqa":
        return ""
    return (getattr(project, "catalog_section_reason", "") or
            "Manba va mamlakat asosida bo‘limni ishonchli aniqlab bo‘lmadi.")
