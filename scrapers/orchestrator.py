"""Scraping orchestrator — runs scrapers in parallel with batch inserts.

Uses ThreadPoolExecutor to run up to MAX_CONCURRENT_PORTALS portals
simultaneously. Each portal scrapes all roles sequentially, with an
early-stop if 2 consecutive roles yield 0 new jobs.
"""

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from core import config as cfg
from core.database import (
    insert_job, insert_jobs_batch, log_scrape_end, log_scrape_start,
)
from scrapers.naukri import NaukriScraper
from scrapers.internshala import InternshalaScraper
from scrapers.timesjobs import TimesJobsScraper
from scrapers.foundit import FounditScraper
from scrapers.iimjobs import IimJobsScraper
from scrapers.shine import ShineScraper
from scrapers.indeed import IndeedScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.glassdoor import GlassdoorScraper

# Registry: portal_name → scraper class
SCRAPER_REGISTRY = {
    "naukri":      NaukriScraper,
    "internshala": InternshalaScraper,
    "timesjobs":   TimesJobsScraper,
    "foundit":     FounditScraper,
    "iimjobs":     IimJobsScraper,
    "shine":       ShineScraper,
    "indeed":      IndeedScraper,
    "linkedin":    LinkedInScraper,
    "glassdoor":   GlassdoorScraper,
}


def _scrape_single_portal(
    portal_name: str,
    role_terms: list[str],
    location: str,
    batch_id: str,
) -> dict:
    """Scrape one portal for all roles. Runs in a worker thread.

    Returns: {portal, found, new, status, error}
    """
    log_id = log_scrape_start(portal_name, batch_id=batch_id)
    portal_found = 0
    portal_new = 0
    error_msg = None
    consecutive_empty = 0

    try:
        scraper_cls = SCRAPER_REGISTRY[portal_name]
        scraper = scraper_cls()

        for role in role_terms:
            # Early-stop: skip remaining roles if 2 in a row yielded 0 new jobs
            if consecutive_empty >= 2:
                break

            try:
                jobs = scraper.fetch_jobs(role=role, location=location)
                portal_found += len(jobs)

                # Batch insert all jobs from this role
                new_count = insert_jobs_batch(jobs) if jobs else 0
                portal_new += new_count

                if new_count == 0:
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0

            except Exception as e:
                error_msg = f"{role}: {str(e)}"

    except Exception as e:
        error_msg = traceback.format_exc()

    # Detect selector drift
    if portal_found == 0 and error_msg is None:
        status = "SELECTOR_DRIFT"
        error_msg = "Portal returned 0 jobs with HTTP 200 — possible selector change"
    else:
        status = "success" if error_msg is None else "partial" if portal_new > 0 else "error"

    log_scrape_end(log_id, portal_found, portal_new, status=status, error=error_msg)

    return {
        "portal": portal_name,
        "found": portal_found,
        "new": portal_new,
        "status": status,
        "error": error_msg,
    }


def run_all_scrapers(
    portals: Optional[list[str]] = None,
    roles: Optional[list[str]] = None,
    location: str = cfg.PRIMARY_LOCATION,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> dict:
    """Run all (or selected) scrapers in parallel batches.

    Args:
        portals: list of portal names to scrape (default: all in config)
        roles: list of role search terms (default: from config)
        location: primary location string
        progress_callback: called with (message, current_step, total_steps)

    Returns:
        Summary dict with total_found, total_new, per-portal results, errors
    """
    portals = portals or cfg.PORTALS
    role_terms: list[str] = []
    if roles:
        role_terms = roles
    else:
        for term_list in cfg.ROLE_SEARCH_TERMS.values():
            role_terms.extend(term_list)
        role_terms = list(dict.fromkeys(role_terms))  # deduplicate, preserve order

    # Filter to valid portals
    valid_portals = [p for p in portals if p in SCRAPER_REGISTRY]

    summary = {
        "total_found": 0,
        "total_new": 0,
        "portals": {},
        "errors": [],
    }

    batch_id = uuid.uuid4().hex[:8]
    total_steps = len(valid_portals)
    completed = 0

    with ThreadPoolExecutor(max_workers=cfg.MAX_CONCURRENT_PORTALS) as executor:
        futures = {
            executor.submit(
                _scrape_single_portal, portal_name, role_terms, location, batch_id
            ): portal_name
            for portal_name in valid_portals
        }

        for future in as_completed(futures):
            completed += 1
            portal_name = futures[future]

            try:
                result = future.result()
            except Exception as e:
                result = {
                    "portal": portal_name,
                    "found": 0,
                    "new": 0,
                    "status": "error",
                    "error": str(e),
                }

            summary["total_found"] += result["found"]
            summary["total_new"] += result["new"]
            summary["portals"][result["portal"]] = {
                "found": result["found"],
                "new": result["new"],
                "status": result["status"],
            }
            if result.get("error"):
                summary["errors"].append(f"{result['portal']}: {result['error']}")

            if progress_callback:
                progress_callback(
                    f"Done: {result['portal']} ({result['new']} new)",
                    completed,
                    total_steps,
                )

    return summary
