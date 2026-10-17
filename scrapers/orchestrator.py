"""Scraping orchestrator — runs all enabled scrapers, deduplicates, and persists jobs.

Runs scrapers sequentially (not parallel) to avoid triggering rate limits
simultaneously across portals. Writes to scrape_log for each portal.
"""

import traceback
from typing import Callable, Optional

from core import config as cfg
from core.database import insert_job, log_scrape_end, log_scrape_start
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


def run_all_scrapers(
    portals: Optional[list[str]] = None,
    roles: Optional[list[str]] = None,
    location: str = cfg.PRIMARY_LOCATION,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> dict:
    """Run all (or selected) scrapers for all target roles.

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

    summary = {
        "total_found": 0,
        "total_new": 0,
        "portals": {},
        "errors": [],
    }

    total_steps = len(portals)
    step = 0

    for portal_name in portals:
        step += 1
        if portal_name not in SCRAPER_REGISTRY:
            continue

        if progress_callback:
            progress_callback(f"Scraping {portal_name}...", step, total_steps)

        log_id = log_scrape_start(portal_name)
        portal_found = 0
        portal_new = 0
        error_msg = None

        try:
            scraper_cls = SCRAPER_REGISTRY[portal_name]
            scraper = scraper_cls()

            for role in role_terms:
                try:
                    jobs = scraper.fetch_jobs(role=role, location=location)
                    portal_found += len(jobs)

                    for job in jobs:
                        inserted = insert_job(job)
                        if inserted:
                            portal_new += 1

                except Exception as e:
                    # Role-level failure — log but continue with next role
                    error_msg = f"{role}: {str(e)}"

        except Exception as e:
            error_msg = traceback.format_exc()
            summary["errors"].append(f"{portal_name}: {str(e)}")

        # Detect selector drift: 0 jobs found with no errors suggests HTML changed
        if portal_found == 0 and error_msg is None:
            status = "SELECTOR_DRIFT"
            error_msg = "Portal returned 0 jobs with HTTP 200 — possible selector change"
        else:
            status = "success" if error_msg is None else "partial" if portal_new > 0 else "error"

        log_scrape_end(log_id, portal_found, portal_new, status=status, error=error_msg)

        summary["total_found"] += portal_found
        summary["total_new"] += portal_new
        summary["portals"][portal_name] = {
            "found": portal_found,
            "new": portal_new,
            "status": status,
        }

    return summary
