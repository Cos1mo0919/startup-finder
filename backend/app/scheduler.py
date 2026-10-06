from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .dates import TASHKENT
from .pipeline import Pipeline


def hourly_trigger():
    return CronTrigger(minute=0, second=0, timezone=TASHKENT)


def run_once(settings, factory, archive=False):
    pipeline = Pipeline(settings, factory)
    try:
        return pipeline.run(archive=archive)
    finally:
        pipeline.close()


def make_scheduler(settings, factory):
    scheduler = BackgroundScheduler(timezone=TASHKENT)
    scheduler.add_job(
        run_once,
        hourly_trigger(),
        args=[settings, factory],
        id="discovery",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    return scheduler
