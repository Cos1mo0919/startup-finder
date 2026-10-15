"""Reproduce SQLAlchemy's autocommit toggle and verify checkout/lease cleanup offline."""

from types import SimpleNamespace

import psycopg
import pytest
from psycopg.pq import TransactionStatus
from sqlalchemy import event, exc, select
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from backend.app.connection_pool import clean_postgres_checkout
from backend.app.db import Lease, Run
from backend.app.free_budget import ACTIVE, BudgetStop
from backend.app.catalog_pipeline import CatalogPipeline
from tests.conftest import FakeDiscovery
from tests.test_free_daily import publishing_pipeline, seed_candidates
from backend.app.free_daily import run_daily


class Connection:
    def __init__(self, status):
        self.info = SimpleNamespace(transaction_status=status)
        self.closed, self.rollbacks, self.toggles = False, 0, 0

    @property
    def autocommit(self):
        return False

    @autocommit.setter
    def autocommit(self, value):
        self.toggles += 1
        if self.info.transaction_status == TransactionStatus.ACTIVE:
            raise psycopg.ProgrammingError(
                "can't change 'autocommit' now: connection in transaction status ACTIVE"
            )
        raise AssertionError("Checkout must never toggle autocommit")

    def rollback(self):
        assert self.info.transaction_status != TransactionStatus.ACTIVE
        self.rollbacks += 1
        self.info.transaction_status = TransactionStatus.IDLE

    def cursor(self):
        parent = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, query):
                assert query == "SELECT 1"
                parent.info.transaction_status = TransactionStatus.INTRANS

            def fetchone(self):
                return (1,)

        return Cursor()


def test_original_sqlalchemy_pre_ping_reproduces_exact_active_error():
    connection = Connection(TransactionStatus.ACTIVE)
    with pytest.raises(psycopg.ProgrammingError, match="can't change 'autocommit'.*ACTIVE"):
        PGDialect_psycopg().do_ping(connection)
    assert connection.toggles == 1


@pytest.mark.parametrize("status", [TransactionStatus.ACTIVE, TransactionStatus.UNKNOWN])
def test_active_socket_is_discarded_without_rollback_or_toggle(status):
    connection = Connection(status)
    with pytest.raises(exc.DisconnectionError):
        clean_postgres_checkout(connection, None, None)
    assert connection.toggles == connection.rollbacks == 0


@pytest.mark.parametrize(
    "status", [TransactionStatus.IDLE, TransactionStatus.INTRANS, TransactionStatus.INERROR]
)
def test_checkout_cleans_transaction_without_changing_autocommit(status):
    connection = Connection(status)
    clean_postgres_checkout(connection, None, None)
    assert connection.info.transaction_status == TransactionStatus.IDLE
    assert connection.toggles == 0
    assert connection.rollbacks == (1 if status == TransactionStatus.IDLE else 2)


def test_interrupted_probe_is_invalidated_instead_of_reused():
    connection = Connection(TransactionStatus.IDLE)

    def cursor():
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, query):
                connection.info.transaction_status = TransactionStatus.ACTIVE
                raise BudgetStop("max_run_seconds")

        return Cursor()

    connection.cursor = cursor
    invalidated = []
    with pytest.raises(BudgetStop):
        clean_postgres_checkout(connection, SimpleNamespace(invalidate=invalidated.append), None)
    assert len(invalidated) == 1 and connection.toggles == 0


@pytest.mark.parametrize("initialization", [False, True])
def test_catalog_releases_lease_even_when_run_persistence_fails(settings, factory, initialization):
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([]))

    def fail_run(session, context, objects):
        if any(
            isinstance(row, Run) and (initialization or row.status != "running")
            for row in [*session.new, *session.dirty]
        ):
            raise RuntimeError("Fixture Run write failure")

    event.listen(factory, "before_flush", fail_run)
    try:
        with pytest.raises(RuntimeError, match="Fixture Run write failure"):
            pipeline.run(discover=False, reanalyze=False)
    finally:
        event.remove(factory, "before_flush", fail_run)
        pipeline.close()
    with factory() as session:
        assert session.get(Lease, "pipeline").owner == ""
        assert session.scalar(select(Lease.name)) == "pipeline"


def test_close_failure_releases_outer_lease_and_clears_context(settings, factory):
    seed_candidates(factory, ["FailureFixture"])

    def pipeline(config, factory):
        instance = publishing_pipeline(config, factory)

        def close():
            instance.web.close()
            raise RuntimeError("Fixture close failure")

        instance.close = close
        return instance

    result = run_daily(settings, factory, pipeline_factory=pipeline)
    assert result["status"] == "failed" and ACTIVE.get() is None
    with factory() as session:
        assert session.get(Lease, "pipeline").owner == ""


def test_postgres_engine_disables_autocommit_toggling_pre_ping():
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import reset_rollback
    from backend.app.connection_pool import runtime_engine

    engine = runtime_engine(make_url("postgresql+psycopg://unused@127.0.0.1/unused"))
    try:
        assert engine.pool._pre_ping is False
        assert engine.pool._reset_on_return == reset_rollback
    finally:
        engine.dispose()


def test_outer_report_failure_still_releases_lease(settings, factory):
    seed_candidates(factory, ["OuterReportFailure"])

    def fail_report(session, context, objects):
        if any(
            isinstance(row, Run) and row.details.get("mode") == "free_daily" and row.status != "running"
            for row in session.dirty
        ):
            raise RuntimeError("Fixture outer report failure")

    event.listen(factory, "before_flush", fail_report)
    try:
        with pytest.raises(RuntimeError, match="Fixture outer report failure"):
            run_daily(settings, factory, pipeline_factory=publishing_pipeline)
    finally:
        event.remove(factory, "before_flush", fail_report)
    assert ACTIVE.get() is None
    with factory() as session:
        assert session.get(Lease, "pipeline").owner == ""
