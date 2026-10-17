"""Internshala scraper — best portal for freshers in India.

Selectors verified against live page structure (September 2026).
"""

import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://internshala.com"

ROLE_SLUG_MAP = {
    "data analyst":          "data-analyst",
    "business intelligence": "business-analyst",
    "bi analyst":            "business-analyst",
    "business analyst":      "business-analyst",
    "finance analyst":       "finance",
    "financial analyst":     "finance",
    "mis analyst":           "data-analyst",
    "reporting analyst":     "data-analyst",
}


class InternshalaScraper(BaseScraper):
    portal_name = "internshala"

    def fetch_jobs(self, role: str, location: str = "india") -> list[dict]:
        slug = _role_to_slug(role)
        jobs: list[dict] = []

        for page in range(1, self.max_pages + 1):
            url = f"{BASE_URL}/jobs/{slug}-jobs-in-india/page-{page}/"
            resp = self._get(url)
            if resp is None:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            # Verified selector: div.individual_internship (works as of 2026)
            cards = soup.select("div.individual_internship")

            if not cards:
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_card(self, card) -> dict | None:
        # Title: h2.job-internship-name a, or a#job_title
        title_tag = card.select_one("h2.job-internship-name a, a#job_title, a.job-title-href")
        if not title_tag:
            return None
        title = title_tag.get_text(strip=True)

        # Apply URL: from data-href on card, or title_tag href
        href = card.get("data-href") or title_tag.get("href", "")
        apply_url = urljoin(BASE_URL, href)

        # Company: p.company-name
        company_tag = card.select_one("p.company-name, .company_name, h4.company_name")
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"

        # Location: p.locations span
        loc_tag = card.select_one("p.locations span, .internship_item_location span")
        location = loc_tag.get_text(strip=True) if loc_tag else "India"

        # Salary: div.row-1-item span.desktop (money icon sibling)
        salary = ""
        for item in card.select("div.row-1-item"):
            if item.select_one("i.ic-16-money"):
                span = item.select_one("span.desktop, span")
                if span:
                    salary = span.get_text(strip=True)
                    break

        # JD: div.about_job div.text
        jd_tag = card.select_one("div.about_job div.text, div.about_internship_container")
        jd_text = jd_tag.get_text(separator="\n", strip=True) if jd_tag else ""

        # Posted
        posted_tag = card.select_one(".posted_by_time, .status-info, time")
        posted = posted_tag.get_text(strip=True) if posted_tag else ""

        return self._normalize(
            portal="internshala",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
            experience_min=0,
            experience_max=2,
            salary_range=salary,
            posted_date=posted,
        )


def _role_to_slug(role: str) -> str:
    role_lower = role.lower()
    for key, slug in ROLE_SLUG_MAP.items():
        if key in role_lower:
            return slug
    return "data-analyst"
