"""v3.1 project catalog decisions; the problem analysis remains optional enrichment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import chain
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import lazyload

from .config import ROOT
from .db import Project, Source
from .detection import normalize
from .network import FetchError, canonical_url, public_dns, safe_url

SECTORS = (
    "AI", "FinTech", "HealthTech", "EdTech", "AgriTech", "Logistics",
    "E-commerce", "SaaS", "GovTech", "TravelTech", "Cybersecurity",
    "LegalTech", "HRTech", "FoodTech", "PropTech", "Energy", "Ecology",
    "Mobility", "Media", "MarTech", "Developer Tools", "Other",
)
PROJECT_TYPES = (
    "startup", "product", "university_project", "hackathon_project",
    "research_project", "government_project", "other",
)
STAGES = ("idea", "prototype", "launched", "growing", "unknown")
NEUTRAL_REASON = "insufficient evidence; neutral fallback"
PROMPT_PATH = ROOT / "config/prompts/catalog_classifier_v3.txt"
STOPWORDS = {
    "uz": {"va", "hamda", "uchun", "bilan", "bu", "bir", "shu", "yoki", "ning", "esa"},
    "ru": {"и", "для", "это", "на", "в", "с", "по", "как", "или", "из"},
    "en": {"the", "and", "for", "with", "this", "that", "from", "into", "are", "its"},
}
GENERIC_DESCRIPTIONS = (
    "startup participating in the program", "project presented at the event",
    "one of the finalists", "dastur ishtirokchisi", "tadbirda taqdim etilgan loyiha",
    "finalchilardan biri", "стартап участвует в программе",
    "проект представлен на мероприятии", "один из финалистов",
)


class CatalogScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clarity: int = Field(ge=1, le=10)
    real_product: int = Field(ge=1, le=10)
    novelty: int = Field(ge=1, le=10)
    potential: int = Field(ge=1, le=10)


class ScoreEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    novelty: bool
    potential: bool


class CatalogEntry(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    creator: str | None = None
    official_url: str | None = None
    country: str | None = None
    sector: str = "Other"
    project_type: str = "other"
    stage: str = "unknown"
    what_it_does: str = ""
    description_uz: str = ""
    scores: CatalogScores | None = None
    score_reasons: dict[str, str] = Field(default_factory=dict)
    score_evidence: ScoreEvidence | None = None
    confidence: float = Field(ge=0, le=1)


@dataclass(frozen=True)
class CatalogResult:
    classification: str
    confidence: float
    entries: tuple[CatalogEntry, ...] = ()
    reason: str = ""
    analysis_method: str = "llm"


class ClassifierFailure(Exception):
    def __init__(self, code, rule_code=None, schema_issues=None):
        super().__init__(code)
        self.rule_code = rule_code or code
        self.schema_issues = schema_issues or []


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:[‘’ʻʼ'-][^\W_]+)*", text, re.UNICODE)


def meaningful_words(text: str) -> list[str]:
    stop = set().union(*STOPWORDS.values())
    return [word for word in words(text) if len(word) > 2 and word.casefold() not in stop]


_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)


def _mentioned(fragment: str, text: str) -> bool:
    """Case-insensitive mention bounded so "x.ai" does not match inside "turistx.ai"."""
    pattern = r"(?<![\w.-])(?:https?://)?(?:www\.)?" + re.escape(fragment) + r"(?![\w-])"
    return re.search(pattern, text, re.I) is not None


def supported_official_url(url: str, source_text: str) -> str | None:
    """Return the URL when the source shows it (a bare domain is enough for a site
    root), otherwise None. Comparison ignores case, scheme, "www." and trailing "/"."""
    candidate = url.strip()
    if not _SCHEME.match(candidate):
        candidate = "https://" + candidate
    candidate = re.sub(r"^http://", "https://", candidate, flags=re.I)
    try:
        candidate = safe_url(candidate)
    except FetchError:
        return None
    parts = urlsplit(candidate)
    host = parts.hostname or ""
    bare_host = host.removeprefix("www.")
    if "." not in bare_host:
        return None
    full = (bare_host + parts.path).rstrip("/") + (("?" + parts.query) if parts.query else "")
    if full != bare_host:
        # A specific page (github.com/owner/repo, t.me/channel) must appear as is;
        # falling back to a shared host's root would be a misleading "official" URL.
        return candidate if _mentioned(full, source_text) else None
    return f"https://{host}/" if _mentioned(bare_host, source_text) else None


def validate_entry(entry: CatalogEntry, source_text: str, method: str = "llm") -> None:
    if entry.sector not in SECTORS or entry.project_type not in PROJECT_TYPES or entry.stage not in STAGES:
        raise ClassifierFailure("invalid_enum")
    if normalize(entry.name) not in normalize(source_text):
        raise ClassifierFailure("unsupported_project_name")
    if entry.official_url:
        # official_url is optional: an unsupported URL is dropped, never stored
        # and never a reason to discard an otherwise valid analysis.
        entry.official_url = supported_official_url(entry.official_url, source_text)
    if method == "llm":
        if not 10 <= len(words(entry.description_uz)) <= 15:
            raise ClassifierFailure("invalid_description")
        if entry.scores is None or entry.score_evidence is None:
            raise ClassifierFailure("invalid_score_evidence", "scores_or_evidence_missing")
        for factor in ("novelty", "potential"):
            if not getattr(entry.score_evidence, factor):
                if getattr(entry.scores, factor) != 4 or entry.score_reasons.get(factor) != NEUTRAL_REASON:
                    raise ClassifierFailure("invalid_score_evidence", "neutral_fallback_mismatch")
        if set(entry.score_reasons) != {"clarity", "real_product", "novelty", "potential"}:
            raise ClassifierFailure("invalid_score_evidence", "score_reason_keys")
        for reason in entry.score_reasons.values():
            if not reason or len(words(reason)) > 15:
                raise ClassifierFailure("invalid_score_evidence", "score_reason_length")
        usage = re.search(r"\b(users?|customers?|paying|revenue|active|foydalanuvchi|foydalanmoqda|mijoz(?:lar|i|imiz)?|ishlat|используют|клиент)\b|pulli hamkorlik", source_text, re.I)
        product = re.search(r"\b(launched|available|working|pilot|prototype|demo|ishga tush|prototip|foydalanmoqda|foydalanadi|запущ|прототип)\b", source_text, re.I)
        if entry.scores.real_product >= 8 and not (usage and product):
            raise ClassifierFailure("invalid_score_evidence", "real_product_usage_unsupported")
    else:
        description = entry.description_uz
        if (len(meaningful_words(description)) < 8 or
                normalize(description) in {normalize(entry.name), normalize(source_text[:200])} or
                any(normalize(template) in normalize(description) for template in GENERIC_DESCRIPTIONS)):
            raise ClassifierFailure("insufficient_description")


def parse_classifier_response(payload: dict, source_text: str) -> CatalogResult:
    if not isinstance(payload, dict):
        raise ClassifierFailure("invalid_json_schema")
    kind = payload.get("classification")
    if kind not in {"PROJECT", "MULTI", "NOT_PROJECT"}:
        raise ClassifierFailure("invalid_classification")
    try:
        confidence = float(payload["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError()
        if kind == "NOT_PROJECT":
            return CatalogResult(kind, confidence, reason=str(payload.get("reason") or "not_project"))
        raw_entries = payload.get("entries") if kind == "MULTI" else [payload]
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ClassifierFailure("invalid_json_schema")
        entries = tuple(CatalogEntry.model_validate(raw) for raw in raw_entries)
        for entry in entries:
            validate_entry(entry, source_text)
        return CatalogResult(kind, confidence, entries)
    except ValidationError as exc:
        # Only known schema field paths and machine error types, never input/value/message.
        allowed = set(CatalogEntry.model_fields) | set(CatalogScores.model_fields) | {"novelty", "potential"}
        issues = [{"field": ".".join(str(part) if isinstance(part, int) or part in allowed else "unknown"
                                     for part in error["loc"]), "type": error["type"][:60]}
                  for error in exc.errors(include_url=False, include_input=False)[:12]]
        raise ClassifierFailure("invalid_json_schema", schema_issues=issues) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ClassifierFailure("invalid_json_schema", schema_issues=[{"field": "confidence_or_entries", "type": type(exc).__name__}]) from exc


def apply_neutral_score_fallback(payload: dict) -> dict:
    """Apply conservative caps where source-wide scores cannot prove entry-level evidence."""
    if not isinstance(payload, dict):
        return payload
    entries = payload.get("entries") if payload.get("classification") == "MULTI" else [payload]
    if not isinstance(entries, list):
        return payload
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        evidence, scores, reasons = (entry.get("score_evidence"), entry.get("scores"),
                                     entry.get("score_reasons"))
        if not all(isinstance(value, dict) for value in (evidence, scores, reasons)):
            continue
        for factor in ("novelty", "potential"):
            if evidence.get(factor) is False:
                scores[factor] = 4
                reasons[factor] = NEUTRAL_REASON
        if payload.get("classification") == "MULTI" and isinstance(scores.get("real_product"), int):
            if scores["real_product"] >= 8:
                scores["real_product"] = 7
                reasons["real_product"] = "Entry-level customer use is not independently verified on this page"
    return payload


def decision(result: CatalogResult, entry: CatalogEntry | None = None) -> tuple[str, str]:
    confidence = entry.confidence if entry is not None else result.confidence
    if result.reason == "llm_unavailable":
        return "REVIEW_REQUIRED", "llm_unavailable"
    if result.classification == "NEEDS_EXTRACTION":
        return "REVIEW_REQUIRED", result.reason or "insufficient_evidence"
    if result.classification == "NOT_PROJECT":
        return (("REJECTED", result.reason) if confidence >= 0.7 else
                ("REVIEW_REQUIRED", result.reason if result.analysis_method == "deterministic" else "uncertain_not_project"))
    if result.analysis_method == "deterministic":
        return ("AUTO_PUBLISHED", "trusted_structured_source") if entry else ("REVIEW_REQUIRED", "llm_unavailable")
    if confidence < 0.4:
        return "REJECTED", "low_confidence"
    if confidence < 0.7:
        return "REVIEW_REQUIRED", "low_confidence"
    if not entry or not entry.name or not entry.description_uz:
        return "REVIEW_REQUIRED", "name_unclear"
    if entry.stage == "idea" and entry.scores and entry.scores.real_product <= 2:
        return "REVIEW_REQUIRED", "future_plan_without_product_evidence"
    return "AUTO_PUBLISHED", "llm_verified_project"


class CatalogClassifier:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    def classify(self, article):
        if not self.settings.ai_key:
            return CatalogResult("NOT_PROJECT", 0.5, reason="llm_unavailable", analysis_method="deterministic")
        base = safe_url(self.settings.ai_base_url)
        public_dns(base, {urlsplit(base).hostname} if self.settings.trusted_egress_proxy else ())
        text = article.text[:3800]
        user = (f"Title: {article.title}\nSource: {article.publisher}\n"
                f"Source country hint: {getattr(article, 'country_hint', '')}\n"
                f"Published: {article.published_at or ''}\nURL: {article.url}\n<article>\n{text}\n</article>")
        body = {"model": self.settings.ai_model, "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": PROMPT_PATH.read_text()},
                             {"role": "user", "content": user}]}
        last_reason = "invalid_json_schema"
        for _ in range(2):
            try:
                if self.client:
                    response = self.client.post(base.rstrip("/") + "/chat/completions", json=body,
                                                headers={"Authorization": f"Bearer {self.settings.ai_key}"})
                else:
                    response = httpx.post(base.rstrip("/") + "/chat/completions", json=body,
                                          headers={"Authorization": f"Bearer {self.settings.ai_key}"}, timeout=30)
                response.raise_for_status()
                payload = json.loads(response.json()["choices"][0]["message"]["content"])
                return parse_classifier_response(payload, article.title + "\n" + text)
            except (ClassifierFailure, ValidationError, KeyError, ValueError, json.JSONDecodeError) as exc:
                last_reason = str(exc) if isinstance(exc, ClassifierFailure) else "invalid_json_schema"
            except httpx.HTTPError as exc:
                raise ClassifierFailure("llm_unavailable") from exc
        raise ClassifierFailure(last_reason)


def catalog_score(entry: CatalogEntry) -> float | None:
    if entry.scores is None:
        return None
    return round(sum(entry.scores.model_dump().values()) / 4, 1)


def trusted_page(adapter: str, page_type: str, path: Path) -> bool:
    config = json.loads(path.read_text())
    return any(row["adapter"] == adapter and row["page_type"] == page_type and
               row["trusted_for_deterministic_publish"] is True for row in config["entries"])


def deterministic_entry(article, allowlist: Path) -> CatalogEntry | None:
    if not trusted_page(getattr(article, "adapter", ""), getattr(article, "page_type", ""), allowlist):
        return None
    name = getattr(article, "project_name", "")
    excerpt = getattr(article, "project_description", "")
    if not name or not excerpt:
        return None
    excerpt_words = words(excerpt)
    description = " ".join(excerpt_words[:20])
    entry = CatalogEntry(name=name, confidence=0.9, what_it_does=description,
                         description_uz=description, country=getattr(article, "country_hint", None),
                         sector=getattr(article, "structured_category", None) or "Other",
                         project_type={"startup_profile": "startup", "university_project": "university_project",
                                       "hackathon_entry": "hackathon_project"}.get(article.page_type, "other"),
                         stage="unknown")
    validate_entry(entry, article.title + "\n" + article.text, "deterministic")
    return entry


def duplicate_decision(session, entry: CatalogEntry, source_url: str):
    """Return (certain match, uncertain match); similar names alone never merge."""
    url = canonical_url(source_url)
    names = {normalize(entry.name), *(normalize(alias) for alias in entry.aliases)}
    compact = {re.sub(r"\W", "", name) for name in names}
    for source in session.scalars(select(Source).where(Source.url == url)):
        project = source.project
        other = {project.normalized_project_name, *(normalize(alias) for alias in project.aliases)}
        creator_conflict = bool(entry.creator and project.creator and normalize(entry.creator) != normalize(project.creator))
        if not creator_conflict and (names & other or compact & {re.sub(r"\W", "", name) for name in other}):
            return project, None
    incoming_domain = urlsplit(entry.official_url).hostname if entry.official_url else None
    uncertain = None
    persisted = session.scalars(select(Project).options(lazyload(Project.sources), lazyload(Project.evidence_records)).execution_options(yield_per=50))
    for project in chain(persisted, (row for row in session.new if isinstance(row, Project))):
        existing = {project.normalized_project_name, *(normalize(alias) for alias in project.aliases)}
        same_name = bool(names & existing or compact & {re.sub(r"\W", "", name) for name in existing})
        same_domain = bool(incoming_domain and project.main_url and urlsplit(project.main_url).hostname == incoming_domain)
        creator_conflict = bool(entry.creator and project.creator and normalize(entry.creator) != normalize(project.creator))
        if same_name and creator_conflict:
            uncertain = project
            continue
        if same_name and not creator_conflict and (same_domain or not entry.official_url or not project.main_url):
            return project, None
        similarity = max(SequenceMatcher(None, a, b).ratio() for a in names for b in existing)
        if similarity >= 0.82 and not creator_conflict:
            uncertain = project
    return None, uncertain
