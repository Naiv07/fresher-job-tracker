"""Shine.com scraper — updated for Next.js structure (2026).

Shine uses Next.js SSR. Job cards use CSS module class names like
result-card_card__p42UB. We match on the stable class prefix.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://www.shine.com"

ROLE_SLUG_MAP = {
    "data analyst":          "data-analyst",
    "business intelligence": "business-intelligence-analyst",
    "bi analyst":            "business-intelligence-analyst",
    "business analyst":      "business-analyst",
    "finance analyst":       "finance-analyst",
    "financial analyst":     "financial-analyst",
    "mis analyst":           "mis",
    "reporting analyst":     "reporting-analyst",
}


class ShineScraper(BaseScraper):
    portal_name = "shine"

    def __init__(self) -> None:
        super().__init__()
        # Shine serves a JS-only shell unless these browser-like headers are set
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })

    def fetch_jobs(self, role: str, location: str = "india") -> list[dict]:
        slug = _role_to_slug(role)
        jobs: list[dict] = []

        for page in range(1, self.max_pages + 1):
            url = f"{BASE_URL}/job-search/{slug}-jobs-in-india/"
            params = {"experience": "0-2", "page": page}
            resp = self._get(url, params=params)
            if resp is None:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            # Next.js CSS modules: class names like "result-card_card__XXXXX"
            cards = soup.select("article[class*='result-card_card']")

            if not cards:
                # Fallback: any article with itemtype=ListItem
                cards = soup.select("article[itemtype*='ListItem']")

            if not cards:
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_card(self, card) -> dict | None:
        # Apply URL: meta itemprop="url" or the main <a> href
        url_meta = card.select_one("meta[itemprop='url']")
        apply_url = url_meta.get("content", "") if url_meta else ""
        if not apply_url:
            link_tag = card.select_one("a[href]")
            apply_url = urljoin(BASE_URL, link_tag.get("href", "")) if link_tag else ""

        # Title: h3 with class containing "role" or itemprop="name"
        title_tag = card.select_one("h3[class*='role'], h3[itemprop='name'], h2[itemprop='name']")
        if not title_tag:
            title_tag = card.select_one("h3, h2")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            return None

        # Company: span with class containing "company"
        company_tag = card.select_one("span[class*='company']")
        company = company_tag.get_text(strip=True) if company_tag else "Unknown"

        # Meta items (location, exp, salary): spans with class containing "meta-item"
        meta_items = card.select("span[class*='meta-item'], li[class*='meta']")
        location = ""
        salary = ""
        for item in meta_items:
            text = item.get_text(strip=True)
            # Heuristic: location usually contains city names or "India"
            if any(c in text for c in [",", "India", "Bangalore", "Mumbai", "Delhi", "Hyderabad"]):
                location = text
            elif "₹" in text or "LPA" in text or "lakh" in text.lower():
                salary = text

        if not location:
            location = "India"

        # Posted: span with class containing "posted"
        posted_tag = card.select_one("span[class*='posted']")
        posted = posted_tag.get_text(strip=True) if posted_tag else ""

        return self._normalize(
            portal="shine",
            title=title,
            company=company,
            apply_url=apply_url,
            location=location,
            salary_range=salary,
            posted_date=posted,
        )


def _role_to_slug(role: str) -> str:
    role_lower = role.lower()
    for key, slug in ROLE_SLUG_MAP.items():
        if key in role_lower:
            return slug
    return "data-analyst"
