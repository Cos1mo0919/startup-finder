from datetime import date
import pytest
from sqlalchemy import select
from backend.app.db import Candidate, RejectedCandidate, Run
from backend.app.diagnostics import inspect_candidate
from backend.app.pipeline import Pipeline
from tests.conftest import FakeDiscovery, sample_article


def test_inspection_distinguishes_missing_url_from_quality_rejection(factory):
    url = "https://news.example/project"
    with factory() as session:
        result = inspect_candidate(session, url + "/")
        assert result["status"] == "not_discovered"
        assert result["project"] is None
        assert not session.new and not session.dirty
    with factory.begin() as session:
        session.add(Candidate(url=url, article={}, status="pending", reason="ambiguous_project"))
    with factory() as session:
        result = inspect_candidate(session, url)
        assert result["status"] == "pending"
        assert result["reason"] == "ambiguous_project"
    with factory.begin() as session:
        session.get(Candidate, url).status = "rejected"
        session.get(Candidate, url).reason = "not_project"
        session.add(RejectedCandidate(url=url, reasons=["not_project"]))
    with factory() as session:
        result = inspect_candidate(session, url)
        assert result["status"] == "rejected"
        assert result["stored_rejection_reasons"] == ["not_project"]


@pytest.mark.parametrize(
    "window,discover,mode",
    [
        (None, True, "current_listings"),
        ((date(2022, 1, 1), date(2022, 12, 31)), True, "year_backfill"),
        (None, False, "queue_only"),
    ],
)
def test_run_records_actual_discovery_mode_and_limits(settings, factory, window, discover, mode):
    pipeline = Pipeline(settings, factory, FakeDiscovery([]))
    pipeline.run(archive=True, window=window, discover=discover)
    with factory() as session:
        details = session.scalar(select(Run)).details
        assert details["discovery_mode"] == mode
        assert details["limits"] == {
            "archive_pages": settings.archive_pages,
            "max_candidates": settings.max_candidates,
        }


def test_inspection_reports_published_project_without_mutation(settings, factory):
    article = sample_article("AquaSense")
    Pipeline(settings, factory, FakeDiscovery([article])).run()
    with factory() as session:
        result = inspect_candidate(session, article.url)
        assert result["status"] == "published"
        assert result["project"]["visible"]
        assert result["project"]["stop_reasons"] == []
        assert not session.new and not session.dirty


def test_archive_cli_explains_that_force_is_not_backfill(settings, monkeypatch, capsys):
    from backend.app import cli

    class EmptyPipeline:
        def __init__(self, config, factory):
            from types import SimpleNamespace

            self.discovery = SimpleNamespace(force=False)

        def run(self, **kwargs):
            assert kwargs == {"archive": True, "discover": True}
            assert self.discovery.force
            return {"status": "completed"}

        def close(self):
            pass

    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(cli, "Pipeline", EmptyPipeline)
    monkeypatch.setattr("sys.argv", ["cli", "--archive", "--force-sources"])
    assert cli.main() == 0
    assert "--backfill --from-date 2022-01-01 --to-date 2026-09-30" in capsys.readouterr().err
