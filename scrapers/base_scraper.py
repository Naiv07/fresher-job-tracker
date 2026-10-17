"""Abstract base scraper with session management, rotating UAs, and retry logic."""

import random
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import (
    MAX_PAGES_PER_PORTAL,
    MAX_RETRIES,
    REQUEST_DELAY_MAX,
    REQUEST_DELAY_MIN,
)

# 10+ real browser User-Agent strings for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

PORTAL_NAME = "base"


class BaseScraper(ABC):
    """Base class for all job portal scrapers."""

    portal_name: str = PORTAL_NAME
    max_pages: int = MAX_PAGES_PER_PORTAL

    def __init__(self) -> None:
        self.session = requests.Session()
        self._refresh_ua()

    def _refresh_ua(self) -> None:
        ua = random.choice(USER_AGENTS)
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })

    def _sleep(self) -> None:
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(MAX_RETRIES),
        reraise=False,
    )
    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET with automatic retry and per-request UA rotation."""
        self._refresh_ua()
        self._sleep()
        try:
            resp = self.session.get(url, timeout=15, **kwargs)
            if resp.status_code in (403, 429):
                # Signal drift/block — do not retry
                return None
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            raise  # tenacity will retry

    @abstractmethod
    def fetch_jobs(self, role: str, location: str) -> list[dict]:
        """Return a list of normalized job dicts for the given role + location.

        Each dict must contain at minimum:
            portal, title, company, apply_url, full_jd,
            location, experience_min, experience_max,
            salary_range, company_desc, posted_date
        """

    @staticmethod
    def _normalize(
        portal: str,
        title: str,
        company: str,
        apply_url: str,
        full_jd: str = "",
        location: str = "",
        experience_min: int = 0,
        experience_max: int = 2,
        salary_range: str = "",
        company_desc: str = "",
        posted_date: str = "",
    ) -> dict:
        """Return a consistently shaped job dict."""
        from datetime import datetime, timezone
        from utils.text_cleaner import clean_text
        from utils.deduplicator import make_job_hash

        title    = clean_text(title)
        company  = clean_text(company)
        full_jd  = clean_text(full_jd)
        company_desc = clean_text(company_desc)

        return {
            "portal":         portal,
            "title":          title,
            "company":        company,
            "apply_url":      apply_url.strip(),
            "full_jd":        full_jd,
            "location":       clean_text(location),
            "experience_min": experience_min,
            "experience_max": experience_max,
            "salary_range":   salary_range,
            "company_desc":   company_desc,
            "posted_date":    posted_date,
            "scraped_at":     datetime.now(timezone.utc).isoformat(),
            "job_id_hash":    make_job_hash(portal, title, company, apply_url),
        }
