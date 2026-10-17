from datetime import timedelta
import pytest
from sqlalchemy import select

from backend.app.db import Candidate, Run, SchedulerCheckpoint, now_utc
from backend.app.free_budget import BudgetStop, free_status, state_name
from backend.app.free_daily import profile, run_daily
from backend.app.page_budget import page_key, reset_trial_pages
from tests.test_free_daily import make_budget, seed_candidates
from tests.conftest import FakeDiscovery
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.network import FetchError


def test_trial_and_daily_pages_are_independent(settings, factory):
    trial = make_budget(factory, limits={"pages": (2, 2)}, page_mode="trial")
    trial.reserve("pages")
    trial.reserve("pages")
    with pytest.raises(BudgetStop):
        trial.reserve("pages")
    daily = make_budget(factory, limits={"pages": (3, 3)}, page_mode="daily")
    daily.reserve("pages")
    with factory() as session:
        assert session.get(SchedulerCheckpoint, page_key(trial.day, "trial")).cursor["usage"]["pages"] == 2
        assert session.get(SchedulerCheckpoint, page_key(trial.day, "daily")).cursor["usage"]["pages"] == 1
    config, limits, _ = profile(
        settings.model_copy(update={"daily_pages_per_run": 1, "daily_pages_per_day": 1}), trial=True
    )
    assert limits["pages"] == (40, 40)


def test_legacy_failed_pages_are_excluded_but_audit_preserved(settings, factory):
    for identifier, status, pages in [(107, "failed", 5), (113, "failed", 9), (121, "completed", 6)]:
        with factory.begin() as session:
            session.add(
                Run(
                    id=identifier,
                    started_at=now_utc(),
                    status=status,
                    details={"mode": "free_daily", "trial": True, "usage": {"pages": pages}},
                    counts={},
                )
            )
    trial = make_budget(factory, limits={"pages": (40, 40)}, page_mode="trial")
    with factory() as session:
        state = session.get(SchedulerCheckpoint, trial.pages.key).cursor
        assert state["usage"]["pages"] == 6
        assert sum(state["refunds"].values()) == 14
        assert sum(state["attempts"].values()) == 20
        assert session.get(Run, 107).details["usage"]["pages"] == 5
        assert session.get(Run, 113).details["usage"]["pages"] == 9


def test_failed_pages_refund_is_idempotent_does_not_refund_llm(factory):
    budget = make_budget(factory, page_mode="trial")
    budget.reserve("pages")
    budget.reserve("llm:gemini")
    with factory.begin() as session:
        assert budget.pages.refund(session) == 1
        assert budget.pages.refund(session) == 0
    with factory() as session:
        assert session.get(SchedulerCheckpoint, budget.pages.key).cursor["usage"]["pages"] == 0
        assert session.get(SchedulerCheckpoint, state_name(budget.day)).cursor["usage"]["llm:gemini"] == 1
    assert budget.used["pages"] == 1


def test_interrupted_run_refunded_on_restart_without_resetting_other_attempts(factory):
    first = make_budget(factory, page_mode="trial")
    first.reserve("pages")
    with factory.begin() as session:
        session.get(Run, first.run_id).status = "interrupted"
    second = make_budget(factory, page_mode="trial")
    second.reserve("pages")
    with factory() as session:
        state = session.get(SchedulerCheckpoint, second.pages.key).cursor
        assert state["usage"]["pages"] == 1 and sum(state["attempts"].values()) == 2


def test_preview_is_readonly_reset_protects_state_and_preserves_daily_ai_and_history(factory):
    trial = make_budget(factory, page_mode="trial")
    trial.reserve("pages")
    daily = make_budget(factory, page_mode="daily")
    daily.reserve("pages")
    trial.reserve("llm:groq")
    preview = reset_trial_pages(factory)
    with factory() as session:
        assert session.get(SchedulerCheckpoint, trial.pages.key).cursor["usage"]["pages"] == 1
    trial.reserve("pages")
    with pytest.raises(ValueError, match="changed"):
        reset_trial_pages(factory, apply=True, expected=preview["expected_state"])
    preview = reset_trial_pages(factory)
    assert reset_trial_pages(factory, apply=True, expected=preview["expected_state"])["applied"]
    with factory() as session:
        assert session.get(SchedulerCheckpoint, daily.pages.key).cursor["usage"]["pages"] == 1
        assert session.get(SchedulerCheckpoint, state_name(trial.day)).cursor["usage"]["llm:groq"] == 1
        assert session.get(Run, trial.run_id).details["usage"]["pages"] == 2
    # A later failure from before the reset must not subtract a new run's pages.
    other = make_budget(factory, page_mode="trial")
    other.reserve("pages")
    with factory.begin() as session:
        assert trial.pages.refund(session) == 0
    with factory() as session:
        assert session.get(SchedulerCheckpoint, trial.pages.key).cursor["usage"]["pages"] == 1


def test_reset_preview_does_not_create_ledger(factory):
    result = reset_trial_pages(factory)
    with factory() as session:
        assert session.get(SchedulerCheckpoint, page_key(result["day"], "trial")) is None


def test_fetch_failure_is_not_reported_as_processed_or_a_decision(settings, factory, offline_daily_preflight):
    seed_candidates(factory, ["BlockedFixture"])

    class FailingDiscovery(FakeDiscovery):
        def article(self, *args):
            from backend.app.free_budget import current_budget

            current_budget().reserve("pages")
            raise FetchError("http_403")

    with factory.begin() as session:
        candidate = session.scalar(select(Candidate))
        candidate.article = {"_queued": True, "_fetch_url": candidate.url}

    def pipeline(config, factory):
        return CatalogPipeline(config, factory, FailingDiscovery([]))

    result = run_daily(settings, factory, trial=True, pipeline_factory=pipeline)
    assert result["counts"]["attempted"] == result["counts"]["pipeline_calls_returned"] == 1
    assert result["counts"]["processed"] == result["counts"]["llm_requests"] == 0
    assert result["counts"]["fetch_failed"] == 1
    assert result["candidate_runs"][0]["error_codes"] == ["http_403"]
    assert result["page_budget"]["charged_today"] == 1


def test_failed_worker_pages_refunded_and_reported(settings, factory, offline_daily_preflight):
    seed_candidates(factory, ["CrashFixture"])

    class CrashDiscovery(FakeDiscovery):
        def article(self, *args):
            from backend.app.free_budget import current_budget

            current_budget().reserve("pages")
            raise RuntimeError("Fixture worker crash")

    with factory.begin() as session:
        candidate = session.scalar(select(Candidate))
        candidate.article = {"_queued": True, "_fetch_url": candidate.url}

    def pipeline(config, factory):
        return CatalogPipeline(config, factory, CrashDiscovery([]))

    result = run_daily(settings, factory, trial=True, pipeline_factory=pipeline)
    assert result["status"] == "failed" and result["usage"]["pages"] == 1
    assert result["page_budget"]["refunded"] == 1 and result["page_budget"]["charged_today"] == 0
    with factory() as session:
        assert session.get(Run, result["run_id"]).details["usage"]["pages"] == 1
        assert free_status(session, settings)["page_budgets"]["trial"]["used"] == 0


def test_reset_fingerprint_rejects_day_rollover(factory, monkeypatch):
    trial = make_budget(factory, page_mode="trial")
    trial.reserve("pages")
    preview = reset_trial_pages(factory)
    future = now_utc() + timedelta(days=1)
    monkeypatch.setattr("backend.app.page_budget.now_utc", lambda: future)
    with pytest.raises(ValueError, match="day changed"):
        reset_trial_pages(factory, apply=True, expected=preview["expected_state"])


def test_returned_call_without_selected_work_is_not_a_processed_candidate(settings, factory):
    from backend.app.run_report import candidate_outcome

    seed_candidates(factory, ["UnselectedReview"])
    with factory.begin() as session:
        candidate = session.scalar(select(Candidate))
        candidate.status = "review_required"
        url = candidate.url
    result = candidate_outcome(factory, url, {"id": 1, "status": "completed", "counts": {"candidates": 0}})
    assert result["stage"] == "no_decision" and result["status"] == "review_required"


def test_fetch_budget_stop_is_separate_from_completed_decisions(settings, factory, offline_daily_preflight):
    seed_candidates(factory, ["BudgetFixture"])

    class StoppedDiscovery(FakeDiscovery):
        def article(self, *args):
            from backend.app.free_budget import current_budget

            current_budget().stop("daily_limit:pages")

    with factory.begin() as session:
        candidate = session.scalar(select(Candidate))
        candidate.article = {"_queued": True, "_fetch_url": candidate.url}

    def pipeline(config, factory):
        return CatalogPipeline(config, factory, StoppedDiscovery([]))

    result = run_daily(settings, factory, trial=True, pipeline_factory=pipeline)
    assert result["counts"]["attempted"] == 1 and result["counts"]["processed"] == 0
    assert result["counts"]["budget_stopped"] == 1 and result["counts"]["llm_requests"] == 0
