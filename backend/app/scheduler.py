"""Continuous source checks plus durable reconciliation and deep-scan checkpoints."""

from datetime import timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from .dates import TASHKENT
from .db import RegistrySource, SchedulerCheckpoint, aware, now_utc
from .pipeline import Pipeline
from .catalog_pipeline import CatalogPipeline


def hourly_trigger():
    return CronTrigger(minute=0, second=0, timezone=TASHKENT)


def run_once(settings, factory, archive=False):
    pipeline = CatalogPipeline(settings, factory)
    try:
        return pipeline.run(archive=archive)
    finally:
        pipeline.close()


def drain_once(settings, factory):
    pipeline = CatalogPipeline(settings, factory)
    try:
        return pipeline.run(discover=False, reanalyze=False)
    finally:
        pipeline.close()


def reanalyze_once(settings, factory):
    pipeline = CatalogPipeline(settings, factory)
    try:
        return pipeline.run(discover=False, process=False)
    finally:
        pipeline.close()


def scan_due(name, checkpoint, now):
    local = aware(now).astimezone(TASHKENT)
    if name == "morning":
        slot = local.strftime("%Y-%m-%d") if (local.hour, local.minute) >= (8, 0) else None
    elif name == "evening":
        slot = local.strftime("%Y-%m-%d") if (local.hour, local.minute) >= (23, 30) else None
    elif name == "local_weekly":
        slot = local.strftime("%G-W%V")
    elif name == "global_monthly":
        slot = local.strftime("%Y-%m")
    else:
        raise ValueError(name)
    if slot is None or (checkpoint and (checkpoint.cursor or {}).get("slot") == slot):
        return False
    # Temporary failures retry later, not on every watchdog tick.
    return not checkpoint or not checkpoint.last_attempt_at or aware(checkpoint.last_attempt_at) <= aware(now) - timedelta(hours=1)


def run_deep_scan(settings, factory, name, now=None):
    now = now or now_utc()
    with factory() as session:
        checkpoint = session.get(SchedulerCheckpoint, name)
        if not scan_due(name, checkpoint, now):
            return {"status": "not_due"}
    with factory.begin() as session:
        checkpoint = session.get(SchedulerCheckpoint, name)
        if checkpoint is None:
            checkpoint = SchedulerCheckpoint(name=name, cursor={})
            session.add(checkpoint)
        checkpoint.last_attempt_at = now
    pipeline = CatalogPipeline(settings, factory) if name in ("morning", "evening") else Pipeline(settings, factory)
    try:
        pipeline.discovery.force = name in ("morning", "evening")
        if name in ("local_weekly", "global_monthly"):
            with factory() as session:
                sources = list(session.scalars(select(RegistrySource)))
            pipeline.discovery.allowed_source_ids = {
                s.id for s in sources if s.enabled and (s.provides_problem_signals or s.provides_market_signals)
                and ((s.country == "Uzbekistan") == (name == "local_weekly"))
            }
            if not pipeline.discovery.allowed_source_ids:
                return {"status": "not_configured", "sources": 0}
            pipeline.discovery.force = True
        result = pipeline.run()
        if result["status"] not in ("busy", "failed"):
            local = aware(now).astimezone(TASHKENT)
            slot = local.strftime("%Y-%m-%d") if name in ("morning", "evening") else local.strftime("%G-W%V") if name == "local_weekly" else local.strftime("%Y-%m")
            with factory.begin() as session:
                checkpoint = session.get(SchedulerCheckpoint, name)
                if result["status"] == "completed" or not result["errors"]:
                    checkpoint.cursor = {"slot": slot, "run_id": result["id"]}
                if result["status"] == "completed":
                    checkpoint.last_success_at = now_utc()
                checkpoint.last_processed_item_at = now_utc()
        return result
    finally:
        pipeline.close()


def reconcile_due(settings, factory):
    """Watchdog also runs after restart, so missed cron times are caught up."""
    return {name: run_deep_scan(settings, factory, name) for name in
            ("morning", "evening", "local_weekly", "global_monthly")}


def make_scheduler(settings, factory):
    scheduler = BackgroundScheduler(timezone=TASHKENT)
    scheduler.add_job(run_once, hourly_trigger(), args=[settings, factory], id="discovery",
                      max_instances=1, coalesce=True, misfire_grace_time=300)
    scheduler.add_job(drain_once, "interval", minutes=15, args=[settings, factory],
                      id="raw_processing", max_instances=1, coalesce=True)
    scheduler.add_job(reanalyze_once, "interval", hours=6, args=[settings, factory],
                      id="catalog_reanalysis", max_instances=1, coalesce=True)
    scheduler.add_job(reconcile_due, "interval", minutes=15, args=[settings, factory],
                      id="reconciliation", max_instances=1, coalesce=True, next_run_time=now_utc())
    return scheduler
