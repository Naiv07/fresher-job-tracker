"""Glassdoor India scraper.

Glassdoor embeds Apollo cache JSON in <script> tags on the page.
We attempt to extract structured data from this cache.
Realistic yield: 5-10 jobs per role per run.
SerpAPI fallback is used when SERP_API_KEY is available.
"""

import json
import re

import streamlit as st
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://www.glassdoor.co.in"
SERPAPI_URL = "https://serpapi.com/search"

ROLE_SLUG_MAP = {
    "data analyst":          ("data-analyst", 18),
    "business intelligence": ("business-intelligence-analyst", 33),
    "bi analyst":            ("business-intelligence-analyst", 33),
    "business analyst":      ("business-analyst", 20),
    "finance analyst":       ("finance-analyst", 17),
    "financial analyst":     ("financial-analyst", 18),
    "mis analyst":           ("data-analyst", 18),
    "reporting analyst":     ("analyst", 7),
}


class GlassdoorScraper(BaseScraper):
    portal_name = "glassdoor"
    max_pages = 1   # Glassdoor is strict; accept limited results

    def fetch_jobs(self, role: str, location: str = "India") -> list[dict]:
        serp_key = _get_serp_key()
        if serp_key:
            jobs = self._fetch_via_serpapi(role, location, serp_key)
            if jobs:
                return jobs

        return self._fetch_via_html(role)

    def _fetch_via_serpapi(self, role: str, location: str, api_key: str) -> list[dict]:
        params = {
            "engine": "glassdoor",
            "q": role,
            "l": location,
            "api_key": api_key,
            "num": 20,
        }
        resp = self._get(SERPAPI_URL, params=params)
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []

        raw = data.get("jobs_results", [])
        jobs = []
        for item in raw:
            job = self._parse_serpapi_item(item)
            if job:
                jobs.append(job)
        return jobs

    def _parse_serpapi_item(self, item: dict) -> dict | None:
        title = item.get("title", "")
        company = item.get("company_name", "") or item.get("company", "")
        if not title or not company:
            return None

        apply_url = item.get("job_link") or item.get("share_link", BASE_URL)
        location = item.get("location", "India")
        jd_text = item.get("description", "")
        salary = item.get("salary", "")
        posted = item.get("date_posted", "")

        return self._normalize(
            portal="glassdoor",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
            salary_range=str(salary),
            posted_date=str(posted),
        )

    def _fetch_via_html(self, role: str) -> list[dict]:
        slug, slug_len = _role_to_slug(role)
        url = f"{BASE_URL}/Job/india-{slug}-jobs-SRCH_IL.0,5_IN115_KO6,{6 + slug_len}.htm"
        resp = self._get(url)
        if not resp:
            return []

        # Try Apollo cache JSON
        jobs = self._extract_apollo_cache(resp.text)
        if jobs:
            return jobs

        # Fallback to HTML
        return self._extract_html(resp.text)

    def _extract_apollo_cache(self, html: str) -> list[dict]:
        """Extract job data from Apollo cache embedded in <script> tags."""
        matches = re.findall(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            html,
            re.S,
        )
        for raw_json in matches:
            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            # Apollo cache keys look like JobListing:123456
            jobs = []
            for key, val in data.items():
                if key.startswith("JobListing:") and isinstance(val, dict):
                    job = self._parse_apollo_item(val)
                    if job:
                        jobs.append(job)
            if jobs:
                return jobs
        return []

    def _parse_apollo_item(self, item: dict) -> dict | None:
        title = item.get("jobTitleText", "") or item.get("title", "")
        company_data = item.get("employer") or {}
        company = company_data.get("name", "") if isinstance(company_data, dict) else str(company_data)
        if not title or not company:
            return None

        apply_url = BASE_URL + item.get("jobViewUrl", "/")
        location = (item.get("location") or {}).get("cityStateCountry", "India") if isinstance(item.get("location"), dict) else "India"
        jd_text = item.get("jobDescription", "")
        posted = str(item.get("discoveryDate", ""))

        return self._normalize(
            portal="glassdoor",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
            posted_date=posted,
        )

    def _extract_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("li.react-job-listing, div[data-test='jobListing']")
        jobs = []
        for card in cards:
            title_tag = card.select_one("a[data-test='job-title'], .job-title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            apply_url = href if href.startswith("http") else BASE_URL + href

            company_tag = card.select_one(".employer-name, [data-test='employer-name']")
            company = company_tag.get_text(strip=True) if company_tag else "Unknown"

            loc_tag = card.select_one(".location, [data-test='emp-location']")
            location = loc_tag.get_text(strip=True) if loc_tag else "India"

            job = self._normalize(
                portal="glassdoor",
                title=title,
                company=company,
                apply_url=apply_url,
                location=location,
            )
            jobs.append(job)
        return jobs


def _role_to_slug(role: str) -> tuple[str, int]:
    role_lower = role.lower()
    for key, (slug, length) in ROLE_SLUG_MAP.items():
        if key in role_lower:
            return slug, length
    return "analyst", 7


def _get_serp_key() -> str:
    try:
        return st.secrets.get("SERP_API_KEY", "")
    except Exception:
        return ""
