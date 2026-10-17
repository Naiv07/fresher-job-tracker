"""APScheduler-based background scraping scheduler.

Uses st.cache_resource so the scheduler is created ONCE per Streamlit
process, not once per user session.

The scheduler only runs while a user has an active browser session.
Streamlit Community Cloud idles apps after ~15 min of no activity,
killing the scheduler thread. The page-load staleness check in app.py
compensates for this by auto-triggering a scrape when data is stale.
"""

import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

from core.config import DEFAULT_SCRAPE_INTERVAL_HOURS, STALE_THRESHOLD_HOURS
from core.database import get_last_successful_scrape


def _scrape_job_fn() -> None:
    """The function run by the scheduler on each tick."""
    from scrapers.orchestrator import run_all_scrapers
    try:
        run_all_scrapers()
    except Exception:
        pass  # Errors are logged inside run_all_scrapers via scrape_log


@st.cache_resource
def get_scheduler(interval_hours: int = DEFAULT_SCRAPE_INTERVAL_HOURS):
    """Create and start the background scheduler (singleton via cache_resource)."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return None

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _scrape_job_fn,
        trigger="interval",
        hours=interval_hours,
        id="scrape_all",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    return scheduler


def ensure_scheduler_running(interval_hours: int = DEFAULT_SCRAPE_INTERVAL_HOURS) -> None:
    """Start the scheduler if not already running."""
    sched = get_scheduler(interval_hours)
    if sched and not sched.running:
        try:
            sched.start()
        except Exception:
            pass


def is_data_stale() -> bool:
    """Return True if no successful scrape in the last STALE_THRESHOLD_HOURS."""
    last = get_last_successful_scrape()
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - last_dt
        return age > timedelta(hours=STALE_THRESHOLD_HOURS)
    except Exception:
        return True


def run_scrape_in_background() -> None:
    """Trigger a one-off scrape in a daemon thread (non-blocking)."""
    t = threading.Thread(target=_scrape_job_fn, daemon=True)
    t.start()
