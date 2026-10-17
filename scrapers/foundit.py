"""Foundit.in (formerly Monster India) scraper.

Foundit is a Next.js SSR app — it embeds a __NEXT_DATA__ JSON blob in a
<script> tag that contains all job listings. We extract this without full
DOM parsing.
"""

import json
import re
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper

BASE_URL = "https://www.foundit.in"
SEARCH_URL = f"{BASE_URL}/srp/results"


class FounditScraper(BaseScraper):
    portal_name = "foundit"

    def __init__(self) -> None:
        super().__init__()
        self.session.headers.update({
            "Accept-Language": "en-IN,en;q=0.9",
        })

    def fetch_jobs(self, role: str, location: str = "India") -> list[dict]:
        jobs: list[dict] = []

        for page in range(1, self.max_pages + 1):
            params = {
                "query": role,
                "location": location,
                "experience": "0-2",
                "freshness": "14",
                "start": (page - 1) * 15,
            }
            resp = self._get(SEARCH_URL, params=params)
            if resp is None:
                break

            page_jobs = self._extract_from_next_data(resp.text)
            if not page_jobs:
                page_jobs = self._extract_from_html(resp.text)

            if not page_jobs:
                break

            jobs.extend(page_jobs)

        return jobs

    def _extract_from_next_data(self, html: str) -> list[dict]:
        """Try to parse __NEXT_DATA__ JSON blob."""
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        # Navigate the nested Next.js data structure
        try:
            page_props = data["props"]["pageProps"]
            job_list = (
                page_props.get("jobList")
                or page_props.get("jobs")
                or page_props.get("data", {}).get("jobList", [])
            )
        except (KeyError, TypeError):
            return []

        if not isinstance(job_list, list):
            return []

        results = []
        for item in job_list:
            job = self._parse_item(item)
            if job:
                results.append(job)
        return results

    def _extract_from_html(self, html: str) -> list[dict]:
        """Fallback HTML scraping."""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.jobCardContainer, div.job-card, article.job-listing")
        results = []
        for card in cards:
            job = self._parse_html_card(card)
            if job:
                results.append(job)
        return results

    def _parse_item(self, item: dict) -> dict | None:
        title = item.get("jobTitle") or item.get("title", "")
        company = item.get("company") or item.get("companyName", "")
        if not title or not company:
            return None

        job_id = item.get("jobId") or item.get("id", "")
        apply_url = item.get("jobUrl") or f"{BASE_URL}/job-details/{job_id}"

        location = ""
        if isinstance(item.get("locations"), list) and item["locations"]:
            location = item["locations"][0].get("label", "") if isinstance(item["locations"][0], dict) else str(item["locations"][0])
        elif isinstance(item.get("location"), str):
            location = item["location"]

        jd_text = item.get("jobDescription", "") or item.get("description", "")
        company_desc = item.get("companyDescription", "") or item.get("aboutCompany", "")
        salary = item.get("salary", "") or item.get("salaryRange", "")
        posted = str(item.get("postedDate", "") or item.get("createdOn", ""))

        exp_min = item.get("minExperience", 0) or 0
        exp_max = item.get("maxExperience", 2) or 2

        return self._normalize(
            portal="foundit",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
            experience_min=int(exp_min),
            experience_max=int(exp_max),
            salary_range=str(salary),
            company_desc=company_desc,
            posted_date=posted,
        )

    def _parse_html_card(self, card) -> dict | None:
        title_tag = card.select_one("h3 a, .job-title a, h2 a")
        if not title_tag:
            return None
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        apply_url = href if href.startswith("http") else BASE_URL + href

        company_tag = card.select_one(".company-name, .companyName")
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"

        loc_tag = card.select_one(".location, .job-location")
        location = loc_tag.get_text(strip=True) if loc_tag else "India"

        jd_tag = card.select_one(".job-description, .job-snippet")
        jd_text = jd_tag.get_text(separator="\n", strip=True) if jd_tag else ""

        return self._normalize(
            portal="foundit",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
        )
