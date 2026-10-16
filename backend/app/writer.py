"""Shared lease for ingestion, admin writes and auxiliary workers."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from functools import wraps
from uuid import uuid4

from sqlalchemy import or_, update

from .db import Lease, now_utc

OWNER = ContextVar("izlanish_writer", default=None)


class WriterBusy(RuntimeError):
    pass


def current_writer(factory):
    owner = OWNER.get()
    return owner[1] if owner and owner[0] is factory.kw["bind"] else None


def renew_writer(factory):
    from .telemetry import span
    with span("lock_wait"):
        return _renew_writer(factory)


def _renew_writer(factory):
    value = OWNER.get()
    if not current_writer(factory):
        return
    now = now_utc()
    with factory.begin() as session:
        changed = session.execute(update(Lease).where(Lease.name == "pipeline", Lease.owner == value[1],
                                  Lease.expires_at > now).values(expires_at=now + timedelta(seconds=value[2]))).rowcount
    if not changed:
        raise WriterBusy("writer_lease_lost")


@contextmanager
def writer_scope(factory, seconds=3300, mark_interrupted=False):
    if current_writer(factory):
        yield current_writer(factory)
        return
    owner, now = str(uuid4()), now_utc()
    with factory.begin() as session:
        changed = session.execute(update(Lease).where(Lease.name == "pipeline",
                                  or_(Lease.owner == "", Lease.expires_at <= now))
                                  .values(owner=owner, expires_at=now + timedelta(seconds=seconds))).rowcount
    if not changed:
        raise WriterBusy("another_writer_active")
    token = OWNER.set((factory.kw["bind"], owner, seconds))
    try:
        if mark_interrupted:
            from .db import Run
            with factory.begin() as session:
                session.execute(update(Run).where(Run.status == "running").values(
                    status="interrupted", finished_at=now, errors=[{"code": "previous_run_interrupted"}]))
        yield owner
    finally:
        OWNER.reset(token)
        with factory.begin() as session:
            session.execute(update(Lease).where(Lease.name == "pipeline", Lease.owner == owner)
                            .values(owner="", expires_at=now_utc()))


@contextmanager
def writer_session(factory):
    with writer_scope(factory):
        with factory.begin() as session:
            yield session


def serialized_worker(function):
    @wraps(function)
    def run(settings, factory, *args, **kwargs):
        try:
            with writer_scope(factory):
                return function(settings, factory, *args, **kwargs)
        except WriterBusy:
            return {"status": "busy"}
    return run


def registry_writer(function):
    @wraps(function)
    def run(factory, *args, **kwargs):
        with writer_scope(factory):
            return function(factory, *args, **kwargs)
    return run
