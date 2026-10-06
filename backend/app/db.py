from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
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
    sources: Mapped[list["Source"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    publisher: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    quotes: Mapped[list] = mapped_column(JSON, default=list)
    project: Mapped[Project] = relationship(back_populates="sources")


class Candidate(Base):
    __tablename__ = "candidates"
    url: Mapped[str] = mapped_column(Text, primary_key=True)
    article: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    reason: Mapped[str] = mapped_column(String(100), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Run(Base):
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

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        if session.get(Lease, "pipeline") is None:
            session.add(Lease(name="pipeline", expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    return engine, factory
