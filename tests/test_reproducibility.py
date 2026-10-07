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


def test_pending_list_and_stable_id_do_not_reprocess(factory):
    from backend.app.diagnostics import list_candidates

    with factory.begin() as session:
        for index, reason in enumerate(["ambiguous_project", "missing_creator", "insufficient_evidence"]):
            session.add(
                Candidate(
                    url=f"https://news.example/{index}",
                    article={"title": f"Article {index}"},
                    status="pending",
                    reason=reason,
                    attempts=2,
                )
            )
        session.add(
            Candidate(
                url="https://news.example/rejected", article={}, status="rejected", reason="not_project"
            )
        )
    with factory() as session:
        report = list_candidates(session)
        assert report["count"] == 3
        assert {r["pending_reason"] for r in report["items"]} == {
            "ambiguous_project",
            "missing_creator",
            "insufficient_evidence",
        }
        for row in report["items"]:
            assert inspect_candidate(session, row["id"]) == row
            assert row["attempts"] == 2
        assert inspect_candidate(session, "sha256:missing")["status"] == "not_found"
        assert list_candidates(session, "rejected")["count"] == 1
        assert not session.new and not session.dirty


def test_debug_report_detects_archive_drift_without_resetting_operator_settings(settings, factory):
    import json
    from pydantic import SecretStr
    from backend.app.db import RegistrySource
    from backend.app.diagnostics import debug_report

    settings.sources_file.write_text(
        json.dumps(
            [
                {
                    "id": "news",
                    "name": "News",
                    "url": "https://news.example/",
                    "options": {"archive": {"sitemap_index": "https://news.example/index.xml"}},
                }
            ]
        )
    )
    settings.ai_api_key = SecretStr("secret-ai-test-value")
    settings.search_api_key = SecretStr("secret-search-test-value")
    with factory.begin() as session:
        session.add(
            RegistrySource(id="news", name="News", url="https://news.example/", enabled=False, options={})
        )
        session.add(
            Run(
                status="partial",
                details={"window": ["2022-01-01", "2022-12-31"]},
                errors=[{"source_id": "news", "stage": "source", "code": "http_403"}],
            )
        )
        for _ in range(6):
            session.add(Run(status="partial", details={"discovery_mode": "queue_only"}))
    with factory() as session:
        result = debug_report(session, settings)
        assert result["sources"][0]["archive_matches_seed"] is False
        assert result["sources"][0]["seed_archive_configured"] is True
        assert result["sources"][0]["enabled"] is False
        assert any(r["errors"] for r in result["runs"])  # drain runs must not hide backfill failures
        assert result["settings"]["ai_enabled"] is True
        assert "secret-ai-test-value" not in json.dumps(result)
        assert "secret-search-test-value" not in json.dumps(result)
        assert not session.new and not session.dirty
        assert session.get(RegistrySource, "news").options == {}


def test_debug_cli_does_not_start_pipeline(settings, monkeypatch, capsys, tmp_path):
    import json
    from backend.app import cli

    monkeypatch.setattr(cli, "Settings", lambda: settings)

    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only diagnostics must not start discovery")

    monkeypatch.setattr(cli, "Pipeline", forbidden)
    destination = tmp_path / "debug.json"
    monkeypatch.setattr("sys.argv", ["cli", "--debug-report", "--report", str(destination)])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["pending"]["count"] == 0
    assert json.loads(destination.read_text()) == result
