"""Email notification sender using smtplib + Jinja2 HTML templates.

SECURITY: SMTP password is NEVER stored in the database.
It is read exclusively from st.secrets["GMAIL_APP_PASSWORD"] at send time.
"""

import smtplib
import traceback
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import streamlit as st
from jinja2 import Template

from core.database import get_notification_config, mark_jobs_notified

# ── HTML email template ───────────────────────────────────────────────────────

EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<style>
  body { font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 0; }
  .container { max-width: 640px; margin: 20px auto; background: white; border-radius: 8px; overflow: hidden; }
  .header { background: #4F46E5; color: white; padding: 20px 24px; }
  .header h1 { margin: 0; font-size: 20px; }
  .header p  { margin: 4px 0 0; opacity: 0.85; font-size: 13px; }
  .stats { display: flex; gap: 16px; padding: 16px 24px; background: #EEF2FF; }
  .stat  { text-align: center; }
  .stat .num { font-size: 24px; font-weight: bold; color: #4F46E5; }
  .stat .lbl { font-size: 11px; color: #6B7280; }
  .job-card { border: 1px solid #E5E7EB; border-radius: 8px; margin: 12px 24px; padding: 16px; }
  .job-title { font-size: 16px; font-weight: bold; color: #111827; margin: 0 0 4px; }
  .company   { font-size: 13px; color: #6B7280; margin: 0 0 4px; }
  .meta      { font-size: 12px; color: #9CA3AF; margin: 0 0 8px; }
  .score-badge { display: inline-block; padding: 2px 10px; border-radius: 99px; font-size: 12px; font-weight: bold; margin-bottom: 8px; }
  .score-high   { background: #D1FAE5; color: #065F46; }
  .score-medium { background: #FEF3C7; color: #92400E; }
  .score-low    { background: #FEE2E2; color: #991B1B; }
  .apply-btn { display: inline-block; background: #4F46E5; color: white; text-decoration: none; padding: 8px 18px; border-radius: 6px; font-size: 13px; margin-top: 8px; }
  .footer { padding: 16px 24px; font-size: 11px; color: #9CA3AF; border-top: 1px solid #E5E7EB; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>New Jobs Found 🎯</h1>
    <p>{{ date }} · {{ total_jobs }} new matching jobs</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="num">{{ total_jobs }}</div><div class="lbl">New Jobs</div></div>
    <div class="stat"><div class="num">{{ high_match }}</div><div class="lbl">Strong Matches</div></div>
    <div class="stat"><div class="num">{{ portals }}</div><div class="lbl">Portals</div></div>
  </div>

  {% for job in jobs %}
  <div class="job-card">
    <div class="job-title">{{ job.title }}</div>
    <div class="company">{{ job.company }} &nbsp;·&nbsp; {{ job.portal | title }}</div>
    <div class="meta">
      📍 {{ job.location or 'India' }}
      {% if job.salary_range %}&nbsp;·&nbsp; 💰 {{ job.salary_range }}{% endif %}
    </div>

    {% if job.match_score is not none %}
      {% if job.match_score >= 70 %}
        <span class="score-badge score-high">{{ job.match_score | int }}% Match</span>
      {% elif job.match_score >= 50 %}
        <span class="score-badge score-medium">{{ job.match_score | int }}% Match</span>
      {% else %}
        <span class="score-badge score-low">{{ job.match_score | int }}% Match</span>
      {% endif %}
    {% endif %}

    {% if job.company_desc %}
    <p style="font-size:12px;color:#6B7280;margin:6px 0;">{{ job.company_desc[:200] }}…</p>
    {% endif %}

    <a href="{{ job.apply_url }}" class="apply-btn">Apply Now →</a>
  </div>
  {% endfor %}

  <div class="footer">
    You're receiving this because you set up job alerts in your Fresher Job Tracker.
    Open the app to manage your preferences or change your notification settings.
  </div>
</div>
</body>
</html>
"""


# ── Sender ────────────────────────────────────────────────────────────────────

def send_job_alert(jobs: list[dict]) -> tuple[bool, str]:
    """Send an HTML email with the given job listings.

    Returns (success, error_message).
    """
    cfg = get_notification_config()
    if not cfg or not cfg.get("is_enabled"):
        return False, "Notifications disabled or not configured."

    smtp_password = _get_smtp_password()
    if not smtp_password:
        return False, "GMAIL_APP_PASSWORD not found in secrets."

    email_to  = cfg["email_to"]
    smtp_host = cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = cfg.get("smtp_port", 587)
    smtp_user = cfg.get("smtp_user", "")

    high_match = sum(1 for j in jobs if (j.get("match_score") or 0) >= 70)
    portals_set = {j.get("portal", "") for j in jobs}

    html_body = Template(EMAIL_TEMPLATE).render(
        date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        total_jobs=len(jobs),
        high_match=high_match,
        portals=len(portals_set),
        jobs=jobs,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Job Alert] {len(jobs)} new fresher jobs found — Data/Finance/BI Analyst"
    msg["From"]    = smtp_user
    msg["To"]      = email_to
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        # Mark jobs as notified only after successful send
        job_ids = [j["id"] for j in jobs if j.get("id")]
        mark_jobs_notified(job_ids)
        return True, ""

    except smtplib.SMTPException as e:
        return False, str(e)
    except Exception as e:
        return False, traceback.format_exc()


def send_test_email() -> tuple[bool, str]:
    """Send a test email with a dummy job entry."""
    dummy_jobs = [{
        "id": 0,
        "title": "Data Analyst",
        "company": "Test Company Pvt Ltd",
        "portal": "naukri",
        "location": "Bangalore, India",
        "salary_range": "3-5 LPA",
        "match_score": 78,
        "company_desc": "This is a test email from your Fresher Job Tracker.",
        "apply_url": "https://example.com/apply",
    }]
    return send_job_alert(dummy_jobs)


def notify_new_jobs(resume_id: Optional[int] = None, min_score: float = 0.0) -> dict:
    """Check for un-notified jobs and send an email if configured.

    Called after each scrape run by the orchestrator.
    Returns summary dict.
    """
    from core.database import get_unnotified_jobs

    cfg = get_notification_config()
    if not cfg or not cfg.get("is_enabled"):
        return {"sent": 0, "skipped": 0, "reason": "disabled"}

    effective_min_score = max(min_score, cfg.get("min_match_score", 0.0))
    jobs = get_unnotified_jobs(min_score=effective_min_score, resume_id=resume_id)

    if not jobs:
        return {"sent": 0, "skipped": 0, "reason": "no new jobs"}

    success, error = send_job_alert(jobs)
    if success:
        return {"sent": len(jobs), "skipped": 0}
    else:
        return {"sent": 0, "skipped": len(jobs), "error": error}


def _get_smtp_password() -> str:
    try:
        return st.secrets.get("GMAIL_APP_PASSWORD", "")
    except Exception:
        import os
        return os.getenv("GMAIL_APP_PASSWORD", "")
