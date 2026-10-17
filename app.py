"""Fresher Job Tracker — entry point."""

import streamlit as st

from core.database import get_last_successful_scrape, init_db, count_jobs, get_active_resume, get_analysis_stats
from core.scheduler import ensure_scheduler_running, is_data_stale, run_scrape_in_background
from core.config import DEFAULT_SCRAPE_INTERVAL_HOURS
from styles import inject_css

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fresher Job Tracker",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

# ── Init ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def _initialize():
    init_db()
    ensure_scheduler_running(DEFAULT_SCRAPE_INTERVAL_HOURS)
    return True

_initialize()

# ── API key check ────────────────────────────────────────────────────────────
try:
    has_ai_key = bool(st.secrets.get("ANTHROPIC_API_KEY", ""))
except Exception:
    has_ai_key = False

# ── Stale data banner ────────────────────────────────────────────────────────
if is_data_stale():
    last = get_last_successful_scrape()
    age_msg = f"Last scraped: {last[:19].replace('T', ' ')} UTC" if last else "Never scraped"
    col1, col2 = st.columns([5, 1])
    with col1:
        st.info(f"Data may be stale. {age_msg}")
    with col2:
        if st.button("Refresh", type="primary", use_container_width=True):
            with st.spinner("Scraping..."):
                run_scrape_in_background()
            st.toast("Scrape started in background.")

# ── Hero ─────────────────────────────────────────────────────────────────────
st.markdown("")
st.title("Fresher Job Tracker")
st.caption("Data Analyst  /  BI Analyst  /  Finance Analyst  —  0-2 yrs  —  India")

if not has_ai_key:
    st.warning(
        "Anthropic API key not set. AI features are disabled. "
        "Add `ANTHROPIC_API_KEY` to `.streamlit/secrets.toml`."
    )

# ── Stats ────────────────────────────────────────────────────────────────────
st.markdown("")
try:
    total_jobs = count_jobs()
    recent_jobs = count_jobs(days=7)
    resume = get_active_resume()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Jobs", f"{total_jobs:,}")
    c2.metric("Last 7 Days", f"{recent_jobs:,}")

    if resume:
        stats = get_analysis_stats(resume["id"])
        c3.metric("Analyzed", f"{stats.get('total', 0):,}")
        avg = stats.get("avg_score")
        c4.metric("Avg Match", f"{avg:.0f}%" if avg else "—")
    else:
        c3.metric("Analyzed", "—")
        c4.metric("Avg Match", "—")
except Exception:
    pass

# ── Navigation ───────────────────────────────────────────────────────────────
st.markdown("")
st.markdown("## Quick access")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        '<div class="nav-card">'
        '<h3>Job Feed</h3>'
        '<p>Browse and filter jobs across all portals. See match scores.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_Job_Feed.py", label="Open Job Feed")

with c2:
    st.markdown(
        '<div class="nav-card">'
        '<h3>Resume Analyzer</h3>'
        '<p>Upload your resume and get AI match scores for every job.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/2_Resume_Analyzer.py", label="Upload Resume")

with c3:
    st.markdown(
        '<div class="nav-card">'
        '<h3>Notifications</h3>'
        '<p>Set up email alerts when new matching jobs are found.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/3_Notifications.py", label="Configure Alerts")

with c4:
    st.markdown(
        '<div class="nav-card">'
        '<h3>Settings</h3>'
        '<p>Manage portals, scrape frequency, API keys, and data.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/4_Settings.py", label="Open Settings")

# ── Resume prompt ────────────────────────────────────────────────────────────
if not get_active_resume():
    st.markdown("")
    st.info("Upload your resume on the Resume Analyzer page to get match scores.")
