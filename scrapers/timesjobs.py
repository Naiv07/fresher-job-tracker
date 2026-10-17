"""TimesJobs scraper using its internal search endpoint.

SSL errors are handled by disabling verification (their cert chain is
sometimes incomplete from cloud servers — safe for read-only scraping).
"""

import re
import warnings

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://www.timesjobs.com"
SEARCH_URL = f"{BASE_URL}/candidate/job-search.html"


class TimesJobsScraper(BaseScraper):
    portal_name = "timesjobs"

    def fetch_jobs(self, role: str, location: str = "india") -> list[dict]:
        jobs: list[dict] = []

        for page in range(1, self.max_pages + 1):
            params = {
                "from": "submit",
                "actualTxtKeywords": role,
                "searchType": "personalizedSearch",
                "clusterName": "Basic",
                "sequence": str(page),
                "postWeek": "2",
            }
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                self._sleep()
                resp = self.session.get(SEARCH_URL, params=params,
                                        timeout=15, verify=False)
                if resp.status_code not in (200,):
                    break
            except Exception:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("li.clearfix.job-bx")

            if not cards:
                # Try alternate selector
                cards = soup.select("li[class*='job-bx'], div.job-container li")

            if not cards:
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_card(self, card) -> dict | None:
        title_tag = card.select_one("h2 a, .job-title a, header h2 a")
        if not title_tag:
            return None
        title = title_tag.get_text(strip=True)
        apply_url = title_tag.get("href", "").strip()
        if not apply_url.startswith("http"):
            apply_url = BASE_URL + apply_url

        company_tag = card.select_one("h3.joblist-comp-name, .comp-name, h3 a")
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"

        loc_tag = card.select_one("ul.top-jd-dtl li, li.location")
        location = loc_tag.get_text(strip=True) if loc_tag else "India"

        exp_tag = card.select_one(".exp, span[title*='Experience'], .exp-span")
        exp_text = exp_tag.get_text(strip=True) if exp_tag else "0-2 Yrs"
        exp_min, exp_max = _parse_experience(exp_text)

        jd_tag = card.select_one(".list-job-dtl, .job-description, .job-desc")
        jd_text = jd_tag.get_text(separator="\n", strip=True) if jd_tag else ""

        posted_tag = card.select_one(".sim-posted span, .posted-date, time")
        posted = posted_tag.get_text(strip=True) if posted_tag else ""

        return self._normalize(
            portal="timesjobs",
            title=title, company=company, apply_url=apply_url,
            full_jd=jd_text, location=location,
            experience_min=exp_min, experience_max=exp_max,
            posted_date=posted,
        )


def _parse_experience(exp_str: str) -> tuple[int, int]:
    nums = re.findall(r"\d+", exp_str)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    if len(nums) == 1:
        n = int(nums[0])
        return n, n
    return 0, 2
