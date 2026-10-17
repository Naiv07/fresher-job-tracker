"""iimjobs.com scraper — focused on Finance and Analytics roles in India."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://www.iimjobs.com"

ROLE_SLUG_MAP = {
    "data analyst":          "data-analyst",
    "business intelligence": "business-analyst",
    "bi analyst":            "business-intelligence-analyst",
    "business analyst":      "business-analyst",
    "finance analyst":       "finance-analyst",
    "financial analyst":     "finance-analyst",
    "mis analyst":           "mis-analyst",
    "reporting analyst":     "analyst",
}


class IimJobsScraper(BaseScraper):
    portal_name = "iimjobs"

    def fetch_jobs(self, role: str, location: str = "india") -> list[dict]:
        slug = _role_to_slug(role)
        jobs: list[dict] = []

        for page in range(1, self.max_pages + 1):
            url = f"{BASE_URL}/j/{slug}-0-2-years.html"
            if page > 1:
                url = f"{BASE_URL}/j/{slug}-0-2-years-{page}.html"

            resp = self._get(url)
            if resp is None or resp.status_code == 404:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("div.job-list li, div#jobs-list li, .job_listing_detail")

            if not cards:
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_card(self, card) -> dict | None:
        title_tag = card.select_one("h2 a, .job_title a, h3 a")
        if not title_tag:
            return None
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        apply_url = urljoin(BASE_URL, href)

        company_tag = card.select_one(".company-name, .company_name, h4")
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"

        loc_tag = card.select_one(".location, .job-location, span[title='Location']")
        location = loc_tag.get_text(strip=True) if loc_tag else "India"

        exp_tag = card.select_one(".exp, .experience, span[title='Experience']")
        exp_text = exp_tag.get_text(strip=True) if exp_tag else "0-2 Yrs"
        exp_min, exp_max = _parse_experience(exp_text)

        jd_tag = card.select_one(".job_description, .job-description, .jd-snippet")
        jd_text = jd_tag.get_text(separator="\n", strip=True) if jd_tag else ""

        posted_tag = card.select_one(".posted, .post-date, time")
        posted = posted_tag.get_text(strip=True) if posted_tag else ""

        return self._normalize(
            portal="iimjobs",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
            experience_min=exp_min,
            experience_max=exp_max,
            posted_date=posted,
        )


def _role_to_slug(role: str) -> str:
    role_lower = role.lower()
    for key, slug in ROLE_SLUG_MAP.items():
        if key in role_lower:
            return slug
    return "analyst"


def _parse_experience(exp_str: str) -> tuple[int, int]:
    nums = re.findall(r"\d+", exp_str)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    if len(nums) == 1:
        n = int(nums[0])
        return n, n
    return 0, 2
