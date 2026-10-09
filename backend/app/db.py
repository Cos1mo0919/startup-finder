from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def now_utc():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    normalized_project_name: Mapped[str] = mapped_column(String(200), index=True)
    creator: Mapped[str] = mapped_column(String(300), default="")
    organization: Mapped[str] = mapped_column(String(300), default="")
    country: Mapped[str] = mapped_column(String(100), default="Uzbekistan")
    city: Mapped[str] = mapped_column(String(100), default="")
    event: Mapped[str] = mapped_column(String(300), default="")
    main_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovery_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    audience: Mapped[str] = mapped_column(String(30), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    images: Mapped[list] = mapped_column(JSON, default=list)
    rating: Mapped[float] = mapped_column(Float, default=0, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    rating_components: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_components: Mapped[dict] = mapped_column(JSON, default=dict)
    primary_sector: Mapped[str] = mapped_column(String(50), default="other")
    sectors: Mapped[list] = mapped_column(JSON, default=list)
    visible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    stop_reasons: Mapped[list] = mapped_column(JSON, default=list)
    detection_signals: Mapped[list] = mapped_column(JSON, default=list)
    real_project_confidence: Mapped[float] = mapped_column(Float, default=0)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    problem_statement: Mapped[str] = mapped_column(Text, default="")
    problem_subject: Mapped[str] = mapped_column(String(300), default="")
    problem_scope: Mapped[str] = mapped_column(String(40), default="")
    problem_frequency: Mapped[str] = mapped_column(String(100), default="")
    problem_severity: Mapped[str] = mapped_column(String(100), default="")
    problem_evidence_summary: Mapped[str] = mapped_column(Text, default="")
    problem_gate_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    problem_gate_reason: Mapped[str] = mapped_column(String(100), default="pending_problem_analysis")
    opportunity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    opportunity_grade: Mapped[str] = mapped_column(String(20), default="PENDING")
    opportunity_details: Mapped[dict] = mapped_column(JSON, default=dict)
    publication_status: Mapped[str] = mapped_column(String(30), default="DISCOVERED", index=True)
    publication_reason: Mapped[str] = mapped_column(String(100), default="")
    secondary_problems: Mapped[list] = mapped_column(JSON, default=list)
    evidence_records: Mapped[list["ProjectEvidence"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class Source(Base):
    __tablename__ = "project_sources"
    __table_args__ = (UniqueConstraint("project_id", "url"),)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    quotes: Mapped[list] = mapped_column(JSON, default=list)
    project: Mapped[Project] = relationship(back_populates="sources")


class Candidate(Base):
    origin: Mapped[str] = mapped_column(String(40), default="other")
    processing_version: Mapped[int] = mapped_column(Integer, default=0)
    analysis_mode: Mapped[str] = mapped_column(String(20), default="")
    last_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archive_scope: Mapped[list] = mapped_column(JSON, default=list)
    entity_type: Mapped[str] = mapped_column(String(30), default="IGNORE")
    project_ids: Mapped[list] = mapped_column(JSON, default=list)
    detector_result: Mapped[str] = mapped_column(String(30), default="NEEDS_EXTRACTION")
    review_decision: Mapped[str] = mapped_column(String(30), default="")
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    __tablename__ = "candidates"
    url: Mapped[str] = mapped_column(Text, primary_key=True)
    article: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    reason: Mapped[str] = mapped_column(String(100), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Run(Base):
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class Lease(Base):
    __tablename__ = "leases"
    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    owner: Mapped[str] = mapped_column(String(36), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistrySource(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(Text, unique=True)
    source_type: Mapped[str] = mapped_column(String(50), default="other")
    region: Mapped[str] = mapped_column(String(120), default="Uzbekistan")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    check_frequency: Mapped[int] = mapped_column(Integer, default=480)
    reliability_score: Mapped[float] = mapped_column(Float, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    collection_method: Mapped[str] = mapped_column(String(30), default="manual_config")
    trust_kind: Mapped[str] = mapped_column(String(30), default="unknown")
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    new_projects: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(String(100), default="")
    sector: Mapped[str] = mapped_column(String(80), default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    provides_projects: Mapped[bool] = mapped_column(Boolean, default=False)
    provides_problem_signals: Mapped[bool] = mapped_column(Boolean, default=False)
    provides_market_signals: Mapped[bool] = mapped_column(Boolean, default=False)
    parser_type: Mapped[str] = mapped_column(String(80), default="")
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(300))
    event_type: Mapped[str] = mapped_column(String(50))
    organizer: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    country: Mapped[str] = mapped_column(String(100), default="Uzbekistan")
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    official_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="discovered")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(100), default="")
    evidence_quote: Mapped[str] = mapped_column(Text)


class ProjectEvidence(Base):
    __tablename__ = "project_evidence"
    __table_args__ = (UniqueConstraint("project_id", "url", "evidence_type", "quote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    evidence_type: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    notes: Mapped[str] = mapped_column(Text, default="")
    quote: Mapped[str] = mapped_column(Text)


class RejectedCandidate(Base):
    __tablename__ = "rejected_candidates"
    url: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    evidence_score: Mapped[float] = mapped_column(Float, default=0)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EcosystemSignal(Base):
    __tablename__ = "ecosystem_signals"
    url: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    signal_type: Mapped[str] = mapped_column(String(50))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    quote: Mapped[str] = mapped_column(Text)
    summary_uz: Mapped[str] = mapped_column(Text, default="")
    why_it_matters_uz: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(String(100), default="Uzbekistan")
    region: Mapped[str] = mapped_column(String(120), default="")
    sector: Mapped[str] = mapped_column(String(80), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    intelligence_status: Mapped[str] = mapped_column(String(30), default="ACTIVE")


class Problem(Base):
    __tablename__ = "problems"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title_uz: Mapped[str] = mapped_column(String(300))
    description_uz: Mapped[str] = mapped_column(Text)
    problem_type: Mapped[str] = mapped_column(String(40), default="EVERYDAY")
    scope: Mapped[str] = mapped_column(String(40), default="EVERYDAY", index=True)
    country: Mapped[str] = mapped_column(String(100), default="")
    region: Mapped[str] = mapped_column(String(120), default="")
    sector: Mapped[str] = mapped_column(String(80), default="other")
    affected_users: Mapped[str] = mapped_column(String(300), default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    evidence_level: Mapped[int] = mapped_column(Integer, default=1)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    first_evidence_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProblemEvidence(Base):
    __tablename__ = "problem_evidence"
    __table_args__ = (UniqueConstraint("problem_id", "source_url", "quote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    publication_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    evidence_type: Mapped[str] = mapped_column(String(50), default="PROBLEM_EXISTS")
    confidence: Mapped[float] = mapped_column(Float, default=0)


class ProjectProblemLink(Base):
    __tablename__ = "project_problem_links"
    __table_args__ = (UniqueConstraint("project_id", "problem_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True)
    solution_strength_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_primary_problem: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SolutionIdea(Base):
    __tablename__ = "solution_ideas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True)
    idea_title: Mapped[str] = mapped_column(String(300))
    idea_summary: Mapped[str] = mapped_column(Text)
    target_user: Mapped[str] = mapped_column(String(300))
    proposed_solution: Mapped[str] = mapped_column(Text)
    current_alternatives: Mapped[str] = mapped_column(Text, default="")
    why_current_alternatives_fail: Mapped[str] = mapped_column(Text, default="")
    business_model_hypothesis: Mapped[str] = mapped_column(Text, default="")
    mvp_hypothesis: Mapped[str] = mapped_column(Text, default="")
    main_risks: Mapped[str] = mapped_column(Text, default="")
    evidence_basis: Mapped[list] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(30), default="deterministic")
    status: Mapped[str] = mapped_column(String(30), default="HYPOTHESIS")
    opportunity_details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SchedulerCheckpoint(Base):
    __tablename__ = "scheduler_checkpoints"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_processed_item_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor: Mapped[dict] = mapped_column(JSON, default=dict)


def make_db(url):
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    from .migrations import migrate

    migrate(engine, Base.metadata)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        if session.get(Lease, "pipeline") is None:
            session.add(Lease(name="pipeline", expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    return engine, factory
