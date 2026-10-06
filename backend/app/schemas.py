from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

SourceKind = Literal["official", "university", "event", "news", "unknown"]
CATEGORIES = {
    "ai": "Sun’iy intellekt",
    "technology": "Texnologiya",
    "business": "Biznes",
    "finance": "Moliya va bank",
    "healthcare": "Tibbiyot",
    "education": "Ta’lim",
    "design": "Dizayn",
    "development": "Dasturlash",
    "smart_city": "Aqlli shahar",
    "government": "Davlat xizmatlari",
    "transportation": "Transport",
    "energy": "Energetika",
    "environment": "Ekologiya",
    "agriculture": "Qishloq xo‘jaligi",
    "security": "Xavfsizlik",
    "marketing": "Marketing",
    "ecommerce": "Elektron savdo",
    "robotics": "Robototexnika",
    "science": "Ilm-fan",
    "construction": "Qurilish",
    "logistics": "Logistika",
    "industry": "Sanoat",
    "architecture": "Arxitektura",
    "other": "Boshqa",
}


class Article(BaseModel):
    source_id: str | None = None
    event_id: str | None = None
    parser_version: int = 2
    url: str
    publisher: str
    title: str
    text: str
    published_at: datetime | None = None
    kind: SourceKind = "unknown"
    image_url: str | None = None
    language: str = ""


class Fact(BaseModel):
    text_uz: str = Field(min_length=3, max_length=1500)
    quote: str = Field(min_length=8, max_length=2000)
    source_url: str


class Evidence(BaseModel):
    # Every populated rubric input must name a fact index; scores never come from the model.
    practical: Literal["unknown", "described", "prototype", "in_use"] = "unknown"
    practical_fact: int | None = None
    problem: Literal["unknown", "stated", "demonstrated"] = "unknown"
    problem_fact: int | None = None
    audience: Literal["unknown", "specific", "multiple"] = "unknown"
    audience_fact: int | None = None
    innovation: Literal["unknown", "adaptation", "novel"] = "unknown"
    innovation_fact: int | None = None
    usability: Literal["unknown", "demo", "available", "adopted"] = "unknown"
    usability_fact: int | None = None


class ProblemAnalysis(BaseModel):
    affected_groups_uz: str = Field(default="", max_length=1500)
    severity_uz: str = Field(default="", max_length=1500)
    frequency_uz: str = Field(default="", max_length=1500)
    solution_scope_uz: str = Field(default="", max_length=1500)
    problem_severity_score: float | None = Field(default=None, ge=0, le=10)
    basis_fact_indexes: list[int] = Field(default_factory=list, max_length=20)


class Analysis(BaseModel):
    primary_sector: str = "other"
    sectors: list[str] = Field(default_factory=list, max_length=8)
    problem_analysis: ProblemAnalysis = Field(default_factory=ProblemAnalysis)
    why_now_uz: str = Field(default="", max_length=2500)
    is_project: bool
    uzbekistan_related: bool
    language: Literal["uz"] = "uz"
    name: str = Field(min_length=2, max_length=200)
    creator: str = Field(default="", max_length=300)
    organization: str = Field(default="", max_length=300)
    university: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=100)
    event: str = Field(default="", max_length=300)
    country: Literal["Uzbekistan"] = "Uzbekistan"
    aliases: list[str] = Field(default_factory=list, max_length=10)
    main_url: str | None = None
    links: dict[str, str] = Field(default_factory=dict)
    summary_uz: str = Field(min_length=10, max_length=1500)
    what_uz: str = Field(default="", max_length=3000)
    how_uz: str = Field(default="", max_length=3000)
    problem_uz: str = Field(default="", max_length=2000)
    individual_benefit_uz: str = Field(default="", max_length=1500)
    business_benefit_uz: str = Field(default="", max_length=1500)
    audience: Literal["individual", "business", "both", "unknown"] = "unknown"
    audience_groups: list[str] = Field(default_factory=list, max_length=12)
    category: str = "other"
    keywords: list[str] = Field(default_factory=list, max_length=20)
    advantages_uz: list[str] = Field(default_factory=list, max_length=10)
    limitations_uz: list[str] = Field(default_factory=list, max_length=10)
    facts: list[Fact] = Field(min_length=1, max_length=20)
    ai_analysis_uz: str = Field(default="", max_length=4000)
    evidence: Evidence = Field(default_factory=Evidence)
    analysis_mode: Literal["ai", "extractive"] = "ai"
