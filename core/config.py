"""Central configuration for the Fresher Job Tracker."""

import os

# ── Target roles ────────────────────────────────────────────────────────────
ROLES = [
    "Data Analyst",
    "Business Intelligence Analyst",
    "BI Analyst",
    "Business Analyst",
    "Finance Analyst",
    "Financial Analyst",
    "MIS Analyst",
    "Reporting Analyst",
]

# Short display names mapped to search keywords
ROLE_SEARCH_TERMS = {
    "Data Analyst":     ["data analyst", "data analytics"],
    "BI Analyst":       ["business intelligence analyst", "bi analyst", "bi developer"],
    "Business Analyst": ["business analyst"],
    "Finance Analyst":  ["finance analyst", "financial analyst"],
    "MIS Analyst":      ["mis analyst", "reporting analyst"],
}

# ── Experience range ─────────────────────────────────────────────────────────
EXP_MIN = 0
EXP_MAX = 2   # years

# ── Locations ────────────────────────────────────────────────────────────────
LOCATIONS = [
    "India",
    "Bangalore",
    "Mumbai",
    "Delhi",
    "Hyderabad",
    "Chennai",
    "Pune",
    "Kolkata",
    "Noida",
    "Gurgaon",
]
PRIMARY_LOCATION = "India"

# ── Portals ───────────────────────────────────────────────────────────────────
PORTALS = [
    "naukri",
    "internshala",
    "timesjobs",
    "foundit",
    "iimjobs",
    "shine",
    "indeed",
    "linkedin",
    "glassdoor",
]

# ── Scraper behaviour ─────────────────────────────────────────────────────────
REQUEST_DELAY_MIN = 2.0   # seconds between requests (min)
REQUEST_DELAY_MAX = 4.5   # seconds between requests (max)
MAX_RETRIES = 3
MAX_PAGES_PER_PORTAL = 3  # pages to scrape per role per portal
MAX_CONCURRENT_PORTALS = 3  # parallel scraper threads

# ── Scheduler ────────────────────────────────────────────────────────────────
DEFAULT_SCRAPE_INTERVAL_HOURS = 6
STALE_THRESHOLD_HOURS = 7  # show "data is stale" banner after this many hours

# ── Database ─────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jobs.db")
USE_CLOUD_DB = False  # set True to use Supabase PostgreSQL

# ── AI ────────────────────────────────────────────────────────────────────────
CLAUDE_BATCH_MODEL  = "claude-haiku-4-5-20251001"   # cheap, fast for batch
CLAUDE_DETAIL_MODEL = "claude-sonnet-4-6"            # rich single-job analysis
ANALYSIS_SLEEP_SEC  = 1.2   # sleep between Claude API calls (rate-limit guard)
MAX_RESUME_CHARS    = 6000  # truncate resume text sent to Claude
MAX_JD_CHARS        = 4000  # truncate JD text sent to Claude

# ── Notifications ────────────────────────────────────────────────────────────
DEFAULT_MIN_MATCH_SCORE = 0.0   # notify for all jobs by default
DAILY_DIGEST_UTC_HOUR   = 2     # 02:30 UTC = 08:00 IST
DAILY_DIGEST_UTC_MINUTE = 30
