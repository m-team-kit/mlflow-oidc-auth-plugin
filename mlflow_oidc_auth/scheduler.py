"""Background scheduler for quota reconciliation and trash cleanup."""

import logging
import os
import tempfile
from contextlib import contextmanager
from typing import Generator

from mlflow_oidc_auth.logger import get_logger

logger = get_logger()


class _AppLogHandler(logging.Handler):
    """Forward APScheduler log records through the application logger."""

    def emit(self, record: logging.LogRecord) -> None:
        logger.handle(record)

try:
    import apscheduler  # noqa: F401

    _apscheduler_available = True
except ImportError:
    _apscheduler_available = False
    logger.warning(
        "APScheduler is not installed. Background quota reconciliation and trash cleanup are disabled. "
        "Install apscheduler to enable: pip install apscheduler"
    )


def _create_scheduler():
    """Return AsyncIOScheduler when an event loop is running (Uvicorn/ASGI),
    otherwise BackgroundScheduler for thread-based execution (Gunicorn sync workers)."""
    import asyncio

    try:
        asyncio.get_running_loop()
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        return AsyncIOScheduler()
    except RuntimeError:
        from apscheduler.schedulers.background import BackgroundScheduler

        return BackgroundScheduler()

_scheduler = None


@contextmanager
def _job_lock(job_id: str) -> Generator[bool, None, None]:
    """Acquire a non-blocking file lock for the given job.

    Yields True if the lock was acquired (this worker should run the job),
    or False if another worker already holds it (skip this run).

    Uses the system temp directory so all workers on the same host share
    the same lock file. For multi-host deployments replace this with a
    database or distributed lock.
    """
    from filelock import FileLock, Timeout

    lock_path = os.path.join(tempfile.gettempdir(), f"mlflow_oidc_{job_id}.lock")
    lock = FileLock(lock_path)
    try:
        lock.acquire(timeout=0)
        try:
            yield True
        finally:
            lock.release()
    except Timeout:
        yield False


def _run_reconcile_quotas() -> None:
    with _job_lock("quota_reconcile") as acquired:
        if not acquired:
            logger.debug("Quota reconciliation skipped: another worker is already running it")
            return

        from mlflow_oidc_auth.utils.quota import reconcile_all_quotas

        logger.info("Running reconciliation...")
        reconcile_all_quotas()


def _run_cleanup_trash() -> None:
    with _job_lock("trash_cleanup") as acquired:
        if not acquired:
            logger.debug("Trash cleanup skipped: another worker is already running it")
            return
        from mlflow_oidc_auth.config import config
        from mlflow_oidc_auth.utils.quota import cleanup_trash

        logger.info("Running cleanup...")
        cleanup_trash(config.QUOTA_TRASH_RETENTION_DAYS)

def init_scheduler() -> None:
    """Start the background scheduler. Called once at app startup."""
    global _scheduler

    if not _apscheduler_available:
        return

    from datetime import datetime

    from mlflow_oidc_auth.config import config

    aps_logger = logging.getLogger("apscheduler")
    aps_logger.handlers = [_AppLogHandler()]
    aps_logger.setLevel(logger.level)
    aps_logger.propagate = False

    _scheduler = _create_scheduler()
    _scheduler.add_job(
        _run_reconcile_quotas,
        "interval",
        seconds=config.QUOTA_RECONCILE_INTERVAL_S,
        id="quota_reconcile",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    _scheduler.add_job(
        _run_cleanup_trash,
        "interval",
        seconds=86400,
        id="trash_cleanup",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    _scheduler.start()
    logger.info(
        f"Background scheduler started: quota reconciliation every {config.QUOTA_RECONCILE_INTERVAL_S}s, "
        f"trash cleanup daily (retention: {config.QUOTA_TRASH_RETENTION_DAYS} days)"
    )


def shutdown_scheduler() -> None:
    """Stop the background scheduler. Called at app shutdown."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
        _scheduler = None
