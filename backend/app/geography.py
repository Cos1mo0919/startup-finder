"""Public catalog geography; source provenance is a scope hint, not a country fact."""

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
# Exact official domains verified during source review. A local news article
# about these international products does not establish a local origin.
GLOBAL_PRIMARY_HOSTS = {"flowtica.ai", "virtualaccelerate.com"}


def project_scope(project) -> str:
    """Return Uzbekistan, Global or Unknown without inventing a project's country."""
    country = (project.country or "").strip().casefold()
    if country in {"uzbekistan", "o‘zbekiston", "узбекистан"}:
        return "Uzbekistan"
    if country:
        return "Global"

    primary_host = ((urlsplit(project.main_url).hostname or "").lower().removeprefix("www.")
                    if getattr(project, "main_url", None) else "")
    if primary_host in GLOBAL_PRIMARY_HOSTS:
        return "Global"

    sources = project.sources or []
    ids = {source.source_id for source in sources}
    if ids & LOCAL_SOURCE_IDS:
        return "Uzbekistan"
    if ids & GLOBAL_SOURCE_IDS:
        return "Global"
    urls = [project.discovery_source_url, *(source.url for source in sources)]
    for url in urls:
        host = (urlsplit(url).hostname or "").lower() if url else ""
        if host in LOCAL_HOSTS or host.endswith(".uz"):
            return "Uzbekistan"
        if host in GLOBAL_HOSTS:
            return "Global"
    return "Unknown"
