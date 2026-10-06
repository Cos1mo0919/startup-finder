import hashlib
import json
from datetime import timedelta
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from .db import RegistrySource, aware
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
                continue
            if source is None:
                source = RegistrySource(id=config.id)
                session.add(source)
                added += 1
            fields = config.model_dump(exclude={"kind", "id"})
            for key, value in fields.items():
                setattr(source, key, value)
            source.trust_kind = config.kind
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
        else:
            source.last_success_at = now
            source.consecutive_errors = 0
