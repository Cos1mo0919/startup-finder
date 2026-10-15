import json
import psycopg
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError

from backend.app.db import Candidate, Run
from backend.app.diagnostics import candidate_id
from backend.app.free_daily import run_daily
from backend.app.safe_errors import safe_error
from backend.app.catalog_pipeline import CatalogPipeline
from tests.conftest import FakeDiscovery
from tests.test_free_daily import seed_candidates


def test_db_error_does_not_include_sql_parameters_connections_or_literals():
    driver = psycopg.ProgrammingError(
        "cannot adapt type 'dict' using placeholder '%s' password=sentinel_key\nDETAIL: parameter $1='private data'"
    )
    error = ProgrammingError("INSERT secret_table VALUES (secret_sql)", {"key": "secret_parameter"}, driver)
    report = safe_error(error, function="test.entry", candidate_url="https://fixture.example/private-path")
    encoded = json.dumps(report)
    for forbidden in (
        "sentinel_key",
        "secret_sql",
        "secret_parameter",
        "private data",
        "private-path",
        "secret_table",
    ):
        assert forbidden not in encoded
    assert report["driver_class"] == "ProgrammingError"
    assert "'dict'" in report["message"] and "'%s'" in report["message"]
    assert len(report["message"]) <= 300
    assert report["candidate_id"] == candidate_id("https://fixture.example/private-path")
    error = ProgrammingError(
        "SECRET_SQL", {}, psycopg.ProgrammingError("postgresql://user:password@host/database failed")
    )
    assert "password" not in safe_error(error, function="test")["message"]


def test_arbitrary_exception_payload_is_not_logged():
    report = safe_error(ValueError("private API_KEY secret_payload"), function="safe_function")
    assert "secret_payload" not in json.dumps(report)


def test_worker_persists_safe_driver_error_with_candidate_in_both_runs(settings, factory):
    seed_candidates(factory, ["ProjectWithFailure"])

    class FailingService:
        available = operational = True
        last_attempt_count = 0

        def analyze_source(self, article):
            raise ProgrammingError(
                "SECRET SQL",
                {"secret": "PRIVATE PARAMETER"},
                psycopg.ProgrammingError("cannot adapt type 'dict' using placeholder '%s'"),
            )

        def status(self):
            return []

    def pipeline(config, factory):
        return CatalogPipeline(config, factory, FakeDiscovery([]), llm_service=FailingService())

    result = run_daily(settings, factory, pipeline_factory=pipeline)
    assert result["stop_reason"] == "worker_error"
    with factory() as session:
        outer = session.get(Run, result["run_id"])
        record = outer.errors[0]
        candidate = session.scalar(select(Candidate))
        assert record["candidate_id"] == candidate_id(candidate.url)
        assert record["function"].startswith("catalog_pipeline.")
        assert record["exception_class"] == "ProgrammingError"
        assert outer.details["last_error"] == record
        assert "PRIVATE PARAMETER" not in json.dumps(outer.errors)
        children = session.scalars(select(Run).where(Run.id != outer.id)).all()
        assert children[0].details["last_error"]["driver_class"] == "ProgrammingError"
