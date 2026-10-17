# Fresher Job Tracker

A Streamlit app that aggregates fresher jobs (0–2 years experience) for **Data Analyst, BI Analyst, and Finance Analyst** roles across all major Indian job portals — with AI-powered resume matching, skill gap analysis, and email alerts.

## Features

- **9 Job Portals**: Naukri, Internshala, TimesJobs, Foundit, iimjobs, Shine, Indeed, LinkedIn, Glassdoor
- **AI Resume Matching**: Upload your resume → Claude analyzes every job → get match %, matched/missing skills, improvement tips
- **Email Alerts**: Get notified for new jobs that match your profile (Gmail/SMTP)
- **Skill Gap Chart**: See the most in-demand skills you're missing across all analyzed jobs
- **Modern Dark UI**: Built with Streamlit's wide layout

---

## Quick Start (Local)

### 1. Install dependencies

```bash
cd fresher-job-tracker
pip install -r requirements.txt
```

### 2. Configure secrets

Edit `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY  = "sk-ant-..."          # Required for AI features
GMAIL_USER         = "sender@gmail.com"    # Required for email alerts
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx" # Gmail App Password (not account password)
SERP_API_KEY       = ""                    # Optional: SerpAPI for LinkedIn/Indeed fallback
```

> **Gmail App Password**: Go to [Google Account → Security → App Passwords](https://myaccount.google.com/apppasswords) and generate a 16-char password for "Mail".

### 3. Run

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## First Use Workflow

1. **Open the app** → Click **Settings** → **Scrape Selected Portals Now**
2. **Upload your resume** → Go to **Resume Analyzer** → upload PDF or DOCX
3. **Analyze jobs** → Click **Analyze All Jobs** to run AI matching
4. **Browse matches** → Go to **Job Feed** → sort by "Highest match first"
5. **Set up alerts** → Go to **Notifications** → enter your email → save

---

## Deployment on Streamlit Community Cloud

### Prerequisites
- A public GitHub repository

### Steps

1. Push this project to a public GitHub repo (make sure `data/` and `.streamlit/secrets.toml` are in `.gitignore`)

2. Go to [share.streamlit.io](https://share.streamlit.io) → **New App**

3. Select your repo, set main file to `app.py`, Python version: **3.11**

4. Go to **Advanced Settings → Secrets** and add:

```toml
ANTHROPIC_API_KEY  = "sk-ant-..."
GMAIL_USER         = "yourapp@gmail.com"
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"
SERP_API_KEY       = ""
```

5. Click **Deploy** — first build takes 3–5 minutes

### ⚠️ Streamlit Cloud Persistence Note

Streamlit Community Cloud has an **ephemeral filesystem** — data in `data/jobs.db` is lost on every restart. To fix this:

- **Option A (simple)**: Accept data loss on restart; click "Scrape Now" to repopulate in minutes
- **Option B (recommended)**: Migrate to [Supabase free tier](https://supabase.com) (500MB PostgreSQL). Only `core/database.py` connection factory needs to change.

---

## Project Structure

```
fresher-job-tracker/
├── app.py                  # Main entry point
├── requirements.txt
├── .streamlit/
│   ├── config.toml         # Dark theme
│   └── secrets.toml        # Local dev only (gitignored)
├── core/
│   ├── config.py           # Roles, portals, constants
│   ├── database.py         # SQLite schema + CRUD
│   └── scheduler.py        # APScheduler background scraper
├── scrapers/               # One scraper per portal + orchestrator
├── ai/
│   ├── resume_parser.py    # PDF/DOCX text extraction
│   ├── claude_client.py    # Anthropic API wrapper
│   └── matcher.py          # Match score + skill gap pipeline
├── notifications/
│   └── email_sender.py     # SMTP email alerts
└── pages/
    ├── 1_Job_Feed.py
    ├── 2_Resume_Analyzer.py
    ├── 3_Notifications.py
    └── 4_Settings.py
```

---

## Portal Health

Some portals are more reliable than others:

| Portal | Reliability | Notes |
|--------|-------------|-------|
| Naukri | ⭐⭐⭐⭐⭐ | JSON API, most stable |
| Internshala | ⭐⭐⭐⭐⭐ | Scraping-friendly |
| TimesJobs | ⭐⭐⭐⭐ | JSON endpoint |
| Foundit | ⭐⭐⭐⭐ | Next.js JSON extraction |
| iimjobs | ⭐⭐⭐⭐ | Finance/Analytics focus |
| Shine | ⭐⭐⭐ | HTML scraping |
| Indeed | ⭐⭐⭐ | Cloudflare bypass via cloudscraper |
| LinkedIn | ⭐⭐ | Guest API, strict rate limits |
| Glassdoor | ⭐⭐ | Limited results without login |

If a portal shows `SELECTOR_DRIFT` status in the Settings → Scrape Log, its HTML structure has changed. Update the selectors in the corresponding `scrapers/<portal>.py` file.
