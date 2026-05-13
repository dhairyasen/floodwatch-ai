"""
FloodWatch AI - Background Scheduler (Phase 2)
APScheduler jobs:
  - Weekly email report every Monday 08:00 IST
  - Optional: periodic health-check ping
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = None


def _run_weekly_report():
    """Job function — import here to avoid circular import at module load."""
    try:
        from email_reporter import WeeklyReporter
        reporter = WeeklyReporter()
        result = reporter.send_weekly_report()
        logger.info(f"[Scheduler] Weekly report job completed: {result}")
    except Exception as e:
        logger.error(f"[Scheduler] Weekly report job failed: {e}", exc_info=True)


def _job_listener(event):
    if event.exception:
        logger.error(f"[Scheduler] Job {event.job_id} raised an exception: {event.exception}")
    else:
        logger.info(f"[Scheduler] Job {event.job_id} executed successfully at {datetime.now()}")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("[Scheduler] Already running, skipping init.")
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # Weekly email report — every Monday at 08:00 IST
    _scheduler.add_job(
        _run_weekly_report,
        trigger=CronTrigger(day_of_week='mon', hour=8, minute=0, timezone="Asia/Kolkata"),
        id='weekly_flood_report',
        name='Weekly Flood Email Report',
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1 hr late start
    )

    _scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    _scheduler.start()

    logger.info("[Scheduler] Started — weekly report scheduled every Monday 08:00 IST")
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")


def get_scheduler_status() -> dict:
    if not _scheduler or not _scheduler.running:
        return {'running': False, 'jobs': []}

    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': next_run.isoformat() if next_run else None,
        })

    return {'running': True, 'jobs': jobs}