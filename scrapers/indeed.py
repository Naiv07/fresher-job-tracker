"""Indeed India scraper using cloudscraper for Cloudflare bypass.

Indeed is aggressive with bot detection. We use cloudscraper to bypass
Cloudflare JS challenges. Limit to 1 request per 10 seconds.
Accept 10-15 jobs as a realistic yield per role.
"""

import re
import time
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://in.indeed.com"
SEARCH_URL = f"{BASE_URL}/jobs"


class IndeedScraper(BaseScraper):
    portal_name = "indeed"
    # Override delay to be more conservative for Indeed
    max_pages = 2

    def __init__(self) -> None:
        super().__init__()
        try:
            import cloudscraper
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            self.session.headers.update({
                "Accept-Language": "en-IN,en;q=0.9",
                "Referer": "https://in.indeed.com/",
            })
            self._use_cloudscraper = True
        except ImportError:
            self._use_cloudscraper = False

    def fetch_jobs(self, role: str, location: str = "India") -> list[dict]:
        jobs: list[dict] = []

        for page in range(self.max_pages):
            params = {
                "q": role,
                "l": location,
                "explvl": "entry_level",
                "fromage": "14",
                "start": page * 15,
            }
            # Build URL manually for Indeed (params sometimes get mangled)
            query = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
            url = f"{SEARCH_URL}?{query}"

            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code in (403, 429):
                    break
                if resp.status_code != 200:
                    break
            except Exception:
                break

            time.sleep(10)  # Conservative delay for Indeed

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("div[data-jk]")

            if not cards:
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_card(self, card) -> dict | None:
        job_key = card.get("data-jk", "")

        # Title
        title_tag = card.select_one("h2.jobTitle span[title], h2.jobTitle a span")
        if not title_tag:
            title_tag = card.select_one("h2 a span")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            return None

        # Company
        company_tag = card.select_one("span.companyName, [data-testid='company-name']")
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"

        # Location
        loc_tag = card.select_one("div.companyLocation, [data-testid='text-location']")
        location = loc_tag.get_text(strip=True) if loc_tag else "India"

        # Salary
        salary_tag = card.select_one(".salary-snippet-container, [data-testid='attribute_snippet_testid']")
        salary = salary_tag.get_text(strip=True) if salary_tag else ""

        # Apply URL
        apply_url = f"{BASE_URL}/viewjob?jk={job_key}" if job_key else BASE_URL

        # JD snippet
        jd_tag = card.select_one(".job-snippet, ul.jobCardShelfContainer")
        jd_text = jd_tag.get_text(separator="\n", strip=True) if jd_tag else ""

        # Posted date
        posted_tag = card.select_one("span.date, [data-testid='myJobsStateDate']")
        posted = posted_tag.get_text(strip=True) if posted_tag else ""

        return self._normalize(
            portal="indeed",
            title=title,
            company=company,
            apply_url=apply_url,
            full_jd=jd_text,
            location=location,
            salary_range=salary,
            posted_date=posted,
        )
