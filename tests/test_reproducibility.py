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


def test_archive_repair_is_additive_idempotent_and_preserves_disabled_health(settings, factory):
    import json
    from backend.app.db import RegistrySource
    from backend.app.registry import repair_archive_config

    adapter = {"sitemap_index": "https://news.example/index.xml", "sitemap_pattern": "{year}"}
    settings.sources_file.write_text(
        json.dumps(
            [
                {"id": key, "name": key, "url": f"https://{key}.example/", "options": {"archive": adapter}}
                for key in ["legacy", "custom", "moved"]
            ]
        )
    )
    with factory.begin() as s:
        s.add(
            RegistrySource(
                id="legacy",
                name="Operator name",
                url="https://legacy.example/",
                collection_method="RSS",
                enabled=False,
                priority=1,
                consecutive_errors=4,
                last_error="http_403",
                options={"custom": "preserved"},
            )
        )
        s.add(
            RegistrySource(
                id="custom",
                name="Custom",
                url="https://custom.example/",
                collection_method="RSS",
                options={"archive": {}},
            )
        )
        s.add(
            RegistrySource(
                id="moved",
                name="Moved",
                url="https://different.example/",
                collection_method="RSS",
                options={},
            )
        )
    result = repair_archive_config(factory, settings.sources_file)
    assert result["updated"] == ["legacy"]
    assert repair_archive_config(factory, settings.sources_file)["updated"] == []
    with factory() as s:
        source = s.get(RegistrySource, "legacy")
        assert source.options == {"custom": "preserved", "archive": adapter}
        assert not source.enabled and source.name == "Operator name" and source.priority == 1
        assert source.consecutive_errors == 4 and source.last_error == "http_403"
        assert s.get(RegistrySource, "custom").options == {"archive": {}}
        assert s.get(RegistrySource, "moved").options == {}


def test_legacy_registry_cannot_silently_report_rss_as_yearly_backfill(settings, factory):
    import json
    from backend.app.db import RegistrySource, now_utc
    from backend.app.registry import repair_archive_config
    from backend.app.collectors.sources import Discovery

    settings.sources_file.write_text(
        json.dumps(
            [
                {
                    "id": "news",
                    "name": "News",
                    "url": "https://news.example/rss",
                    "options": {
                        "archive": {
                            "sitemap_index": "https://news.example/index.xml",
                            "sitemap_pattern": "{year}",
                        }
                    },
                }
            ]
        )
    )
    with factory.begin() as s:
        s.add(
            RegistrySource(
                id="news",
                name="News",
                url="https://news.example/rss",
                collection_method="RSS",
                enabled=True,
                options={},
            )
        )

    class Web:
        proxy_hosts = set()

        def get(self, url):
            assert url != "https://news.example/rss", (
                "Yearly traversal must not silently fall back to current RSS"
            )
            if url.endswith("index.xml"):
                return (
                    b"<sitemapindex><sitemap><loc>https://news.example/2022.xml</loc></sitemap></sitemapindex>",
                    url,
                )
            return b"<urlset><url><loc>https://news.example/2022/07/19/project</loc></url></urlset>", url

    discovery = Discovery(settings, Web(), factory=factory)
    discovery.window = (date(2022, 1, 1), date(2022, 12, 31))
    links, errors, _ = discovery.discover(now_utc(), archive=True)
    assert not links and errors[0]["code"] == "archive_configuration_missing"
    from backend.app.radar_api import source_json
    from backend.app.diagnostics import summarize_run

    with factory() as session:
        assert source_json(session.get(RegistrySource, "news"))["status"] == "NEEDS_CONFIG"
    assert summarize_run({}, errors, False)["configuration_errors"] == 1
    assert repair_archive_config(factory, settings.sources_file, "news")["updated"] == ["news"]
    links, errors, _ = discovery.discover(now_utc(), archive=True)
    assert not errors and links[0]["url"] == "https://news.example/2022/07/19/project"
    assert discovery.archive_coverage[0]["pages"] == 1


@pytest.mark.parametrize("article_year,expected", [(2026, "published"), (2025, "rejected")])
def test_rediscovered_queued_url_routes_to_its_year_but_still_verifies_article_date(
    settings, factory, article_year, expected
):
    from datetime import datetime, timezone

    article = sample_article("AquaSense", url="https://news.example/2026/03/10/aqua")
    article.published_at = datetime(article_year, 3, 10, tzinfo=timezone.utc)
    with factory.begin() as session:
        session.add(
            Candidate(
                url=article.url,
                article={"_queued": True, "_fetch_url": article.url},
                status="queued",
                archive_scope=["2022-01-01", "2022-12-31"],
            )
        )
    result = Pipeline(settings, factory, FakeDiscovery([article])).run(
        archive=True, window=(date(2026, 1, 1), date(2026, 9, 30))
    )
    assert result["counts"]["candidates"] == 1
    with factory() as session:
        c = session.get(Candidate, article.url)
        assert c.archive_scope == ["2026-01-01", "2026-09-30"]
        assert c.status == expected
        if expected == "rejected":
            assert c.reason == "outside_archive_window"


def test_rediscovery_does_not_move_old_queued_url_into_unrelated_window(settings, factory):
    article = sample_article("AquaSense", url="https://news.example/2022/07/19/aqua")
    with factory.begin() as session:
        session.add(
            Candidate(
                url=article.url,
                article={"_queued": True},
                status="queued",
                archive_scope=["2022-01-01", "2022-12-31"],
            )
        )
    result = Pipeline(settings, factory, FakeDiscovery([article])).run(
        archive=True, window=(date(2026, 1, 1), date(2026, 9, 30))
    )
    assert result["counts"]["candidates"] == 0
    with factory() as session:
        assert session.get(Candidate, article.url).archive_scope == ["2022-01-01", "2022-12-31"]
