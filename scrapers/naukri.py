"""Naukri.com scraper.

Naukri's internal JSON API (/jobapi/v4/search) returns 404 without
browser-generated session tokens. Instead we use their public mobile/
Algolia-style API which is still accessible, with a fallback to
parsing the JSON-LD embedded in the SEO job-search pages.
"""

import json
import re
import time
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://www.naukri.com"

# Naukri's CDN API used by their mobile app and public pages (2025/2026)
NAUKRI_API = "https://www.naukri.com/jobapi/v4/search"

ROLE_SLUG_MAP = {
    "data analyst":          "data-analyst-jobs",
    "business intelligence": "business-intelligence-analyst-jobs",
    "bi analyst":            "bi-analyst-jobs",
    "business analyst":      "business-analyst-jobs",
    "finance analyst":       "finance-analyst-jobs",
    "financial analyst":     "financial-analyst-jobs",
    "mis analyst":           "mis-analyst-jobs",
    "reporting analyst":     "reporting-analyst-jobs",
}


class NaukriScraper(BaseScraper):
    portal_name = "naukri"

    def __init__(self) -> None:
        super().__init__()
        # Naukri requires a warm session with cookies
        self.session.headers.update({
            "Referer": "https://www.naukri.com/",
            "appid": "109",
            "systemid": "109",
        })
        self._warm_session()

    def _warm_session(self) -> None:
        try:
            self.session.get(BASE_URL, timeout=10)
            time.sleep(1.5)
        except Exception:
            pass

    def fetch_jobs(self, role: str, location: str = "india") -> list[dict]:
        jobs = self._fetch_via_api(role, location)
        if not jobs:
            jobs = self._fetch_via_html(role)
        return jobs

    def _fetch_via_api(self, role: str, location: str) -> list[dict]:
        """Try Naukri's internal API with a full set of browser-like headers."""
        jobs: list[dict] = []
        for page in range(1, self.max_pages + 1):
            params = {
                "noOfResults": 20,
                "urlType": "search_by_key_loc",
                "searchType": "adv",
                "keyword": role,
                "location": location,
                "experience": "0-2",
                "jobAge": 14,
                "src": "jobsearchDesk",
                "pageNo": page,
            }
            headers = {
                "Accept": "application/json",
                "x-http-method-override": "GET",
            }
            try:
                resp = self.session.get(NAUKRI_API, params=params,
                                        headers=headers, timeout=15)
                if resp.status_code != 200:
                    return []
                data = resp.json()
            except Exception:
                return []

            job_list = (
                data.get("responsedata", {}).get("jobDetails", [])
                or data.get("jobDetails", [])
            )
            if not job_list:
                break

            for item in job_list:
                job = self._parse_api_item(item)
                if job:
                    jobs.append(job)

        return jobs

    def _fetch_via_html(self, role: str) -> list[dict]:
        """Scrape Naukri's SEO search-result pages using schema.org JSON-LD."""
        jobs: list[dict] = []
        slug = _role_to_slug(role)

        for page in range(1, self.max_pages + 1):
            if page == 1:
                url = f"{BASE_URL}/{slug}-0-to-2-years"
            else:
                url = f"{BASE_URL}/{slug}-0-to-2-years-{page}"

            resp = self._get(url)
            if resp is None:
                break

            soup = BeautifulSoup(resp.text, "lxml")

            # Try schema.org JobPosting structured data
            ld_scripts = soup.find_all("script", type="application/ld+json")
            for script in ld_scripts:
                try:
                    data = json.loads(script.string or "")
                    # Could be a single JobPosting or an ItemList
                    if isinstance(data, list):
                        items = data
                    elif data.get("@type") == "ItemList":
                        items = data.get("itemListElement", [])
                    elif data.get("@type") == "JobPosting":
                        items = [data]
                    else:
                        continue

                    for item in items:
                        posting = item.get("item", item)  # unwrap ListItem
                        if posting.get("@type") == "JobPosting":
                            job = self._parse_ld_item(posting)
                            if job:
                                jobs.append(job)
                except Exception:
                    continue

            if not jobs and page == 1:
                # Last resort: parse visible job cards from HTML
                jobs.extend(self._parse_html_cards(soup))

            if not jobs:
                break

        return jobs

    def _parse_api_item(self, item: dict) -> Optional[dict]:
        title = item.get("jobTitle", "")
        company = item.get("companyName") or item.get("sgCompanyName", "")
        if not title or not company:
            return None

        job_id = item.get("jobId", "")
        apply_url = item.get("jdURL") or f"{BASE_URL}/{job_id}"

        placeholders = item.get("placeholders", [])
        location_str, salary_range = "", ""
        for ph in placeholders:
            if ph.get("label") == "location":
                location_str = ph.get("title", "")
            elif ph.get("label") == "salary":
                salary_range = ph.get("title", "")

        exp_str = item.get("experienceText", "") or item.get("footerPlaceholderLabel", "")
        exp_min, exp_max = _parse_experience(exp_str)
        jd_text = item.get("jobDescription", "") or item.get("jobSnippet", "")
        company_desc = item.get("companyInfo", {}).get("aboutCompany", "") or ""
        posted = str(item.get("createdDate", ""))

        return self._normalize(
            portal="naukri", title=title, company=company,
            apply_url=apply_url, full_jd=jd_text, location=location_str,
            experience_min=exp_min, experience_max=exp_max,
            salary_range=salary_range, company_desc=company_desc,
            posted_date=posted,
        )

    def _parse_ld_item(self, item: dict) -> Optional[dict]:
        title = item.get("title", "") or item.get("name", "")
        org = item.get("hiringOrganization", {})
        company = org.get("name", "") if isinstance(org, dict) else str(org)
        if not title or not company:
            return None

        apply_url = item.get("url", "") or item.get("sameAs", BASE_URL)
        loc = item.get("jobLocation", {})
        if isinstance(loc, dict):
            addr = loc.get("address", {})
            location = (
                addr.get("addressLocality", "")
                or addr.get("addressRegion", "")
                or "India"
            ) if isinstance(addr, dict) else "India"
        else:
            location = "India"

        jd_text = item.get("description", "")
        salary_val = item.get("baseSalary", {})
        salary = ""
        if isinstance(salary_val, dict):
            val = salary_val.get("value", {})
            if isinstance(val, dict):
                salary = f"{val.get('minValue', '')} - {val.get('maxValue', '')} {val.get('unitText', '')}"

        posted = item.get("datePosted", "")

        return self._normalize(
            portal="naukri", title=title, company=company,
            apply_url=apply_url, full_jd=jd_text, location=location,
            salary_range=salary, posted_date=posted,
        )

    def _parse_html_cards(self, soup) -> list[dict]:
        """Last-resort HTML card parsing for Naukri React pages."""
        jobs = []
        # Naukri uses article tags with class containing 'jobTuple' or 'job-card'
        cards = soup.select(
            "article.jobTuple, div[class*='jobTuple'], "
            "article[class*='job'], div[class*='srp-jobtuple']"
        )
        for card in cards:
            title_tag = card.select_one("a.title, h2 a, .job-title a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            apply_url = title_tag.get("href", BASE_URL)
            company_tag = card.select_one(".comp-name, .company, h3 a")
            company = company_tag.get_text(strip=True) if company_tag else "Unknown"
            loc_tag = card.select_one(".loc-wrap, .location")
            location = loc_tag.get_text(strip=True) if loc_tag else "India"
            job = self._normalize(
                portal="naukri", title=title, company=company,
                apply_url=apply_url, location=location,
            )
            jobs.append(job)
        return jobs


def _role_to_slug(role: str) -> str:
    role_lower = role.lower()
    for key, slug in ROLE_SLUG_MAP.items():
        if key in role_lower:
            return slug
    return "data-analyst-jobs"


def _parse_experience(exp_str: str) -> tuple[int, int]:
    numbers = re.findall(r"\d+", exp_str)
    if len(numbers) >= 2:
        return int(numbers[0]), int(numbers[1])
    if len(numbers) == 1:
        n = int(numbers[0])
        return n, n
    return 0, 2
