"""LinkedIn Jobs scraper using the guest (unauthenticated) API.

LinkedIn is strict about rate-limiting. Strategy:
1. Use the guest search API endpoint (no login required).
2. 5-second minimum delay between requests.
3. Skip on 429 — do NOT retry.
4. Fallback: JSearch RapidAPI if SERP_API_KEY is configured.

LinkedIn HTML response for the guest endpoint returns HTML fragments,
not JSON. Each job card has a data-entity-urn with the job ID.
"""

import json
import re
import time
from urllib.parse import quote_plus

import streamlit as st
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

GUEST_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)
JOB_DETAIL_URL = "https://www.linkedin.com/jobs/view/{job_id}/"
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"


class LinkedInScraper(BaseScraper):
    portal_name = "linkedin"
    max_pages = 2   # LinkedIn blocks quickly; keep low

    def __init__(self) -> None:
        super().__init__()
        self.session.headers.update({
            "Accept": "text/html,*/*",
            "Referer": "https://www.linkedin.com/",
        })

    def fetch_jobs(self, role: str, location: str = "India") -> list[dict]:
        # Try JSearch RapidAPI first (more reliable)
        serp_key = _get_serp_key()
        if serp_key:
            jobs = self._fetch_via_jsearch(role, location, serp_key)
            if jobs:
                return jobs

        # Fall back to guest API
        return self._fetch_via_guest_api(role, location)

    def _fetch_via_jsearch(self, role: str, location: str, api_key: str) -> list[dict]:
        headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        params = {
            "query": f"{role} in {location}",
            "page": "1",
            "num_pages": "2",
            "date_posted": "month",
            "employment_types": "FULLTIME,INTERN",
        }
        try:
            resp = self.session.get(JSEARCH_URL, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()
            raw_jobs = data.get("data", [])
        except Exception:
            return []

        jobs = []
        for item in raw_jobs:
            job = self._parse_jsearch_item(item)
            if job:
                jobs.append(job)
        return jobs

    def _parse_jsearch_item(self, item: dict) -> dict | None:
        title = item.get("job_title", "")
        company = item.get("employer_name", "")
        if not title or not company:
            return None

        apply_url = item.get("job_apply_link") or item.get("job_google_link", "")
        location = item.get("job_city", "") or item.get("job_country", "India")
        jd_text = item.get("job_description", "")
        salary = ""
        if item.get("job_min_salary"):
            salary = f"{item['job_min_salary']} - {item.get('job_max_salary', '')} {item.get('job_salary_currency', '')}"

        posted = str(item.get("job_posted_at_datetime_utc", ""))

        return self._normalize(
            portal="linkedin",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
            salary_range=salary,
            posted_date=posted,
        )

    def _fetch_via_guest_api(self, role: str, location: str) -> list[dict]:
        jobs = []
        for page in range(self.max_pages):
            params = {
                "keywords": role,
                "location": location,
                "f_E": "1,2",          # Entry Level, Associate
                "f_TPR": "r1209600",   # last 2 weeks
                "start": page * 25,
            }
            try:
                resp = self.session.get(GUEST_SEARCH_URL, params=params, timeout=15)
                if resp.status_code in (429, 403):
                    break
                if resp.status_code != 200:
                    break
            except Exception:
                break

            time.sleep(5)  # Strict 5-second delay

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("li[data-entity-urn], div.job-search-card")

            if not cards:
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_card(self, card) -> dict | None:
        # Extract job ID from data-entity-urn
        urn = card.get("data-entity-urn", "")
        job_id = urn.split(":")[-1] if urn else ""

        title_tag = card.select_one("h3.base-search-card__title, h3 a, .job-title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            return None

        company_tag = card.select_one("h4.base-search-card__subtitle a, .company-name")
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"

        loc_tag = card.select_one("span.job-search-card__location, .job-location")
        location = loc_tag.get_text(strip=True) if loc_tag else "India"

        apply_url = JOB_DETAIL_URL.format(job_id=job_id) if job_id else ""
        if not apply_url:
            link_tag = card.select_one("a.base-card__full-link, a")
            apply_url = link_tag.get("href", "") if link_tag else ""

        posted_tag = card.select_one("time, .job-search-card__listdate")
        posted = posted_tag.get("datetime", "") or (posted_tag.get_text(strip=True) if posted_tag else "")

        return self._normalize(
            portal="linkedin",
            title=title,
            company=company,
            apply_url=apply_url,
            posted_date=posted,
            location=location,
        )


def _get_serp_key() -> str:
    try:
        return st.secrets.get("SERP_API_KEY", "")
    except Exception:
        return ""
