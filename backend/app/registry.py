import hashlib
import json
from datetime import timedelta
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from .db import RegistrySource, SourceBlock, aware, now_utc
from .network import safe_url, canonical_url

FREQUENCIES = {5: 60, 4: 180, 3: 480, 2: 1440, 1: 10080}


class SourceConfig(BaseModel):
    id: str = ""
    name: str
    url: str
    source_type: Literal[
        "startup_platform",
        "university",
        "hackathon",
        "accelerator",
        "news",
        "government",
        "company",
        "event",
        "RSS",
        "community",
        "other",
    ] = "news"
    region: str = "Uzbekistan"
    priority: int = Field(default=3, ge=1, le=5)
    check_frequency: int | None = Field(default=None, ge=60, le=525600)
    reliability_score: float = Field(default=5, ge=0, le=10)
    enabled: bool = True
    collection_method: Literal["search", "RSS", "direct_page", "API", "browser", "manual_config"] = "RSS"
    kind: Literal["official", "university", "event", "news", "unknown"] = "news"
    options: dict = Field(default_factory=dict)
    notes: str = ""
    country: str = ""
    sector: str = ""
    purpose: str = ""
    provides_projects: bool = False
    provides_problem_signals: bool = False
    provides_market_signals: bool = False
    parser_type: str = ""

    @model_validator(mode="after")
    def defaults(self):
        self.url = canonical_url(safe_url(self.url))
        self.id = self.id or hashlib.sha256(self.url.encode()).hexdigest()[:24]
        self.check_frequency = self.check_frequency or FREQUENCIES[self.priority]
        return self


def load_sources(path):
    return [SourceConfig.model_validate(s) for s in json.loads(path.read_text())]


def seed_registry(factory, path, update=False):
    configs = load_sources(path)
    added = 0
    with factory.begin() as session:
        for config in configs:
            source = session.get(RegistrySource, config.id) or session.scalar(
                select(RegistrySource).where(RegistrySource.url == config.url)
            )
            if source and not update:
                # A one-time metadata backfill. Later operator edits, including False,
                # must never be undone by ordinary startup.
                if source.updated_at is None:
                    for field in ("country", "sector", "purpose", "parser_type",
                                  "provides_projects", "provides_problem_signals", "provides_market_signals"):
                        setattr(source, field, getattr(config, field))
                    source.updated_at = now_utc()
                continue
            if source is None:
                source = RegistrySource(id=config.id)
                session.add(source)
                added += 1
            fields = config.model_dump(exclude={"kind", "id"})
            with session.no_autoflush:
                last_block = session.scalar(select(SourceBlock).where(SourceBlock.source_id == source.id)
                                            .order_by(SourceBlock.id.desc())) if source.id else None
            for key, value in fields.items():
                if key == "enabled" and last_block and last_block.action == "BLOCK":
                    value = False
                setattr(source, key, value)
            source.trust_kind = config.kind
            source.updated_at = now_utc()
    return added


def due(source, now, force=False):
    return source.enabled and (
        force
        or source.last_checked_at is None
        or aware(source.last_checked_at) + timedelta(minutes=source.check_frequency) <= aware(now)
    )


def source_for_url(session, url):
    host = urlsplit(url).hostname
    sources = list(session.scalars(select(RegistrySource)))
    exact = next((s for s in sources if canonical_url(s.url) == canonical_url(url)), None)
    return exact or next(
        (s for s in sources if urlsplit(s.url).hostname == host and s.collection_method != "search"), None
    )


def ensure_publisher(session, article):
    source = source_for_url(session, article.url)
    if source:
        return source
    host = urlsplit(article.url).hostname
    source = RegistrySource(
        id="discovered-" + hashlib.sha256(host.encode()).hexdigest()[:20],
        name=article.publisher,
        url="https://" + host + "/",
        source_type={"news": "news", "university": "university", "event": "event", "official": "company"}.get(
            article.kind, "other"
        ),
        region="International source covering Uzbekistan",
        priority=1,
        check_frequency=10080,
        reliability_score={"news": 7, "official": 9, "university": 9, "event": 9}.get(article.kind, 3),
        enabled=False,
        collection_method="manual_config",
        trust_kind=article.kind,
        notes="Avtomatik topilgan nashr. Ishonchlilik operator tomonidan tekshirilishi kerak.",
    )
    session.add(source)
    session.flush()
    return source


def record_check(factory, source_id, now, count=0, error=""):
    with factory.begin() as session:
        source = session.get(RegistrySource, source_id)
        source.last_checked_at = now
        source.candidates_found = count
        source.last_error = error
        if error:
            source.consecutive_errors += 1
            source.last_error_at = now
            source.last_http_status = int(error[5:]) if error.startswith("http_") and error[5:].isdigit() else None
        else:
            source.last_success_at = now
            source.consecutive_errors = 0
            source.last_http_status = 200


def repair_archive_config(factory, path, source_id=None):
    """Explicit, additive repair; never reset operator settings or source health."""
    seeds = {source.id: source for source in load_sources(path)}
    updated, skipped = [], []
    with factory.begin() as session:
        query = select(RegistrySource).order_by(RegistrySource.id)
        if source_id:
            query = query.where(RegistrySource.id == source_id)
        sources = list(session.scalars(query))
        if source_id and not sources:
            raise ValueError("Unknown source ID")
        for source in sources:
            seed = seeds.get(source.id)
            if not seed or not seed.options.get("archive"):
                reason = "no_seed_archive"
            elif canonical_url(source.url) != seed.url or source.collection_method != seed.collection_method:
                reason = "source_endpoint_or_method_changed"
            elif "archive" in source.options:
                reason = "archive_key_already_present"
            else:
                source.options = {**source.options, "archive": seed.options["archive"]}
                updated.append(source.id)
                continue
            skipped.append({"id": source.id, "reason": reason})
    return {"updated": updated, "skipped": skipped}
