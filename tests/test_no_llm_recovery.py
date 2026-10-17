"""No production access: keyless preflight, per-mode budgets, diversity and guarded recovery."""

from datetime import timedelta
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from backend.app.candidate_budget import candidate_key
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.dates import TASHKENT
from backend.app.db import Candidate, Lease, RawDiscovery, RegistrySource, Run, SchedulerCheckpoint, now_utc
from backend.app.diagnostics import candidate_id
from backend.app.free_budget import BudgetStop
from backend.app.free_daily import run_daily
from backend.app.no_llm_recovery import RecoveryError, recover_no_llm
from backend.app.raw_discovery import ingest_raw, record_transition
from tests.conftest import FakeDiscovery, sample_article
from tests.test_free_daily import make_budget, PublishingService
from tests.test_daily_postgres import postgres_factory  # noqa: F401


@pytest.mark.parametrize("trial", [True, False])
@pytest.mark.parametrize(
    "confirmed,gemini,groq,enabled",
    [(False, "test", "test", True), (True, "", "", True), (True, "test", "test", False)],
)
def test_no_llm_stops_before_candidate_budget_or_pipeline(
    settings, factory, trial, confirmed, gemini, groq, enabled
):
    url = "https://fixture.example/ready"
    with factory.begin() as session:
        session.add(Candidate(url=url, status="queued", article={"title": "Fixture"}))

    def pipeline(*args):
        pytest.fail("No provider: pipeline must not even be constructed")

    result = run_daily(
        settings.model_copy(
            update={
                "free_provider_quotas_confirmed": confirmed,
                "gemini_api_key": SecretStr(gemini),
                "groq_api_key": SecretStr(groq),
                "llm_enabled": enabled,
            }
        ),
        factory,
        trial=trial,
        pipeline_factory=pipeline,
    )
    assert result["stop_reason"] == "no_llm_provider" and result["counts"]["attempted"] == 0
    assert result["usage"] == {} and result["candidate_runs"] == []
    with factory() as session:
        assert session.get(Candidate, url).status == "queued"
        assert list(session.scalars(select(SchedulerCheckpoint))) == []
        assert session.get(Run, result["run_id"]).details["stop_reason"] == "no_llm_provider"
        assert session.get(Lease, "pipeline").owner == ""


def test_trial_daily_candidates_are_independent(factory):
    limits = {"pages": (10, 10), "candidates": (2, 2)}
    trial = make_budget(factory, limits=limits, page_mode="trial")
    trial.reserve("candidates")
    trial.reserve("candidates")
    with pytest.raises(BudgetStop, match="run_limit:candidates"):
        trial.reserve("candidates")
    daily = make_budget(factory, limits=limits, page_mode="daily")
    daily.reserve("candidates")
    with factory() as session:
        assert (
            session.get(SchedulerCheckpoint, candidate_key(trial.day, "trial")).cursor["usage"]["candidates"]
            == 2
        )
        assert (
            session.get(SchedulerCheckpoint, candidate_key(trial.day, "daily")).cursor["usage"]["candidates"]
            == 1
        )


def configured(settings):
    return settings.model_copy(
        update={"free_provider_quotas_confirmed": True, "gemini_api_key": SecretStr("offline-key")}
    )


@pytest.mark.parametrize("trial,expected", [(True, 3), (False, 6)])
def test_three_per_source_applies_only_to_trial(settings, factory, trial, expected):
    with factory.begin() as session:
        session.add(
            RegistrySource(
                id="one", name="One", url="https://one.example", source_type="startup_platform", enabled=False
            )
        )
        session.flush()
        for name in ["AtlasGarden", "NimbusPay", "VectorScan", "SolarField", "MapleCloud", "CobaltDesk"]:
            article = sample_article(name=name, url=f"https://one.example/{name}")
            session.add(
                Candidate(
                    url=article.url, source_id="one", status="queued", article=article.model_dump(mode="json")
                )
            )
    result = run_daily(
        configured(settings).model_copy(
            update={"daily_project_target": 6, "daily_llm_min_interval_seconds": 0}
        ),
        factory,
        trial=trial,
        pipeline_factory=lambda config, factory: CatalogPipeline(
            config, factory, FakeDiscovery([]), llm_service=PublishingService()
        ),
    )
    assert result["counts"]["attempted"] == expected
    assert result["counts"]["published"] == expected


def seed_missing_key(factory):
    now = now_utc()
    day = now.astimezone(TASHKENT).date().isoformat()
    items = []
    with factory.begin() as session:
        parent = Run(
            id=148,
            status="completed",
            started_at=now,
            counts={"attempted": 20, "llm_requests": 0},
            details={},
        )
        session.add(parent)
        for index in range(19):
            child = 149 + index
            session.add(
                Run(
                    id=child,
                    status="completed",
                    started_at=now,
                    counts={"review_required": 1},
                    details={"mode": "catalog_fresh"},
                )
            )
        session.flush()
        for index in range(19):
            url = f"https://fixture.example/{index}"
            child = 149 + index
            session.add(
                Candidate(
                    url=url,
                    status="review_required",
                    reason="llm_unavailable",
                    last_run_id=child,
                    article={},
                    attempts=1,
                    status_history=[{"value": "REVIEW_REQUIRED", "reason": "llm_unavailable"}],
                )
            )
            raw, _ = ingest_raw(session, source_adapter="fixture", source_url=url, source_name="Fixture")
            raw.candidate_url = url
            record_transition(raw, "review_required", "llm_unavailable")
            items.append(
                {
                    "candidate_id": candidate_id(url),
                    "run_id": child,
                    "stage": "review_required",
                    "reason": "llm_unavailable",
                    "provider_attempts": [
                        {"provider": provider, "outcome": "missing_key", "request_sent": False}
                        for provider in ["gemini", "groq"]
                    ],
                }
            )
        session.add(Candidate(url="https://fixture.example/unprocessed", status="queued", article={}))
        items.append(
            {
                "candidate_id": candidate_id("https://fixture.example/unprocessed"),
                "run_id": 168,
                "stage": "budget_stopped",
                "provider_attempts": [],
            }
        )
        parent.details = {
            "mode": "free_daily",
            "trial": True,
            "day": day,
            "usage": {"candidates": 20},
            "candidate_runs": items,
        }
    return day


@pytest.mark.parametrize("db_fixture", ["factory", "postgres_factory"])
def test_recovery_preview_apply_idempotency_and_preserved_history(request, db_fixture, settings):
    factory = request.getfixturevalue(db_fixture)
    day = seed_missing_key(factory)
    daily = make_budget(factory, limits={"pages": (10, 10), "candidates": (10, 10)}, page_mode="daily")
    daily.reserve("candidates")
    with factory() as session:
        before = session.get(Run, 148).details.copy()
    preview = recover_no_llm(factory, 148, 149, 167)
    assert preview["requeue_count"] == 19 and preview["refund_candidates"] == 20
    assert preview["refund_today"] == 20 and not preview["applied"]
    with factory() as session:
        assert session.get(SchedulerCheckpoint, candidate_key(day, "trial")) is None
        assert session.get(Candidate, "https://fixture.example/0").status == "review_required"
    result = recover_no_llm(factory, 148, 149, 167, apply=True, expected=preview["expected_state"])
    assert result["applied"] and result["candidates_after"] == 0
    with factory() as session:
        candidate = session.get(Candidate, "https://fixture.example/0")
        assert candidate.status == "queued" and candidate.attempts == 1
        assert len(candidate.status_history) == 3
        assert session.get(Run, 148).details == before
        assert session.get(Candidate, "https://fixture.example/unprocessed").status == "queued"
        assert (
            session.get(SchedulerCheckpoint, candidate_key(day, "daily")).cursor["usage"]["candidates"] == 1
        )
        assert session.get(SchedulerCheckpoint, candidate_key(day, "trial")).cursor["attempts"]["148"] == 20
        assert all(
            row.status == "pending" and len(row.processing_history) == 2
            for row in session.scalars(select(RawDiscovery))
        )
    again = recover_no_llm(factory, 148, 149, 167, apply=True, expected=preview["expected_state"])
    assert again["already_applied"] and again["refunded"] == 0


@pytest.mark.parametrize("change", ["candidate", "counter", "day", "provider"])
def test_recovery_rejects_changed_state_without_partial_writes(factory, monkeypatch, change):
    day = seed_missing_key(factory)
    preview = recover_no_llm(factory, 148, 149, 167)
    with factory.begin() as session:
        if change == "candidate":
            session.get(Candidate, "https://fixture.example/0").review_decision = "KEEP_FOR_REVIEW"
        elif change == "counter":
            session.add(
                SchedulerCheckpoint(
                    name=candidate_key(day, "trial"),
                    cursor={
                        "usage": {"candidates": 21},
                        "charges": {"148": 20, "999": 1},
                        "attempts": {"148": 20, "999": 1},
                    },
                )
            )
        elif change == "provider":
            parent = session.get(Run, 148)
            parent.details = {**parent.details, "usage": {"candidates": 20, "llm:groq": 1}}
    if change == "day":
        monkeypatch.setattr("backend.app.no_llm_recovery.now_utc", lambda: now_utc() + timedelta(days=1))
    with pytest.raises(RecoveryError):
        recover_no_llm(factory, 148, 149, 167, apply=True, expected=preview["expected_state"])
    with factory() as session:
        assert session.get(Candidate, "https://fixture.example/1").status == "review_required"
        assert session.get(Lease, "pipeline").owner == ""


def test_recovery_wrong_child_range_is_rejected(factory):
    seed_missing_key(factory)
    with pytest.raises(RecoveryError, match="child_range_not_owned"):
        recover_no_llm(factory, 148, 148, 166)


def test_recovery_transaction_rolls_back_all_rows_on_write_error(factory):
    from sqlalchemy import event

    seed_missing_key(factory)
    preview = recover_no_llm(factory, 148, 149, 167)

    def fail(session, context, instances):
        if any(isinstance(row, Candidate) and row.status == "queued" for row in session.dirty):
            raise RuntimeError("fixture write failure")

    event.listen(factory, "before_flush", fail)
    try:
        with pytest.raises(RuntimeError, match="fixture write failure"):
            recover_no_llm(factory, 148, 149, 167, apply=True, expected=preview["expected_state"])
    finally:
        event.remove(factory, "before_flush", fail)
    with factory() as session:
        assert all(
            row.status == "review_required"
            for row in session.scalars(select(Candidate).where(Candidate.last_run_id.is_not(None)))
        )
        assert all(row.status == "review_required" for row in session.scalars(select(RawDiscovery)))
        assert session.get(SchedulerCheckpoint, candidate_key(preview["budget_day"], "trial")) is None
        assert session.get(Lease, "pipeline").owner == ""


def test_previous_day_recovery_never_credits_today(factory, monkeypatch):
    old_day = seed_missing_key(factory)
    future = now_utc() + timedelta(days=1)
    monkeypatch.setattr("backend.app.no_llm_recovery.now_utc", lambda: future)
    preview = recover_no_llm(factory, 148, 149, 167)
    assert preview["budget_day"] == old_day and preview["refund_today"] == 0
    recover_no_llm(factory, 148, 149, 167, apply=True, expected=preview["expected_state"])
    with factory() as session:
        today = future.astimezone(TASHKENT).date().isoformat()
        assert session.get(SchedulerCheckpoint, candidate_key(today, "trial")) is None
        assert (
            session.get(SchedulerCheckpoint, candidate_key(old_day, "trial")).cursor["usage"]["candidates"]
            == 0
        )


def test_source_cap_selects_other_sources_instead_of_spending_all_on_one(settings, factory):
    with factory.begin() as session:
        session.add_all(
            [
                RegistrySource(
                    id="first",
                    name="First",
                    url="https://first.example",
                    source_type="startup_platform",
                    priority=5,
                    enabled=False,
                ),
                RegistrySource(
                    id="second",
                    name="Second",
                    url="https://second.example",
                    source_type="startup_platform",
                    priority=4,
                    enabled=False,
                ),
            ]
        )
        session.flush()
        for source, names in [
            ("first", ["AtlasGarden", "NimbusPay", "VectorScan", "SolarField"]),
            ("second", ["MapleCloud", "CobaltDesk", "CopperWorks"]),
        ]:
            for name in names:
                article = sample_article(name=name, url=f"https://{source}.example/{name}")
                session.add(
                    Candidate(
                        url=article.url,
                        source_id=source,
                        status="queued",
                        article=article.model_dump(mode="json"),
                    )
                )
    result = run_daily(
        configured(settings).model_copy(update={"daily_llm_min_interval_seconds": 0}),
        factory,
        trial=True,
        pipeline_factory=lambda config, factory: CatalogPipeline(
            config, factory, FakeDiscovery([]), llm_service=PublishingService()
        ),
    )
    assert result["counts"]["attempted"] == 5 and result["counts"]["published"] == 5
    assert result["source_attempts"] == {"id:first": 3, "id:second": 2}
