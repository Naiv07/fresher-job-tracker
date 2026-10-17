"""Settings — manage portals, scraping, API keys, and data."""

import pandas as pd
import streamlit as st

from core.config import DEFAULT_SCRAPE_INTERVAL_HOURS, PORTALS
from core.database import count_jobs, delete_old_jobs, get_jobs, get_scrape_logs
from core.scheduler import run_scrape_in_background
from scrapers.orchestrator import run_all_scrapers
from styles import inject_css

st.set_page_config(page_title="Settings", layout="wide")
inject_css()

st.title("Settings")
st.caption("Manage portals, scraping, API keys, and database")

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_scrape, tab_api, tab_db, tab_logs = st.tabs(["Scrapers", "API Keys", "Database", "Scrape Log"])

# ── Tab 1: Scrapers ──────────────────────────────────────────────────────────
with tab_scrape:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Portals")
        enabled_portals = []
        for portal in PORTALS:
            if st.toggle(portal.title(), value=True, key=f"p_{portal}"):
                enabled_portals.append(portal)

    with col2:
        st.markdown("### Frequency")
        freq_label = st.selectbox(
            "Auto-scrape every",
            options=["3 hours", "6 hours", "12 hours", "24 hours"],
            index=1,
        )

        st.markdown("")
        st.markdown("### Manual scrape")
        if st.button("Scrape selected portals", type="primary", use_container_width=True):
            log_area = st.empty()
            progress = st.progress(0.0, text="Starting...")

            def _cb(msg, step, total):
                progress.progress(step / total, text=msg)

            with st.spinner("Scraping..."):
                summary = run_all_scrapers(
                    portals=enabled_portals,
                    progress_callback=_cb,
                )

            progress.progress(1.0, text="Done")
            st.success(
                f"Found: **{summary['total_found']}**  ·  "
                f"New: **{summary['total_new']}**"
            )

            if summary["errors"]:
                with st.expander("Errors"):
                    for err in summary["errors"]:
                        st.error(err)

# ── Tab 2: API Keys ─────────────────────────────────────────────────────────
with tab_api:
    st.markdown("### Status")
    st.caption("Keys are stored in `.streamlit/secrets.toml` — never in the database.")

    try:
        anthropic_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        gmail_pass    = st.secrets.get("GMAIL_APP_PASSWORD", "")
        serp_key      = st.secrets.get("SERP_API_KEY", "")
    except Exception:
        anthropic_key = gmail_pass = serp_key = ""

    c1, c2, c3 = st.columns(3)
    c1.metric("Anthropic API", "Set" if anthropic_key else "Missing")
    c2.metric("Gmail Password", "Set" if gmail_pass else "Missing")
    c3.metric("SerpAPI (optional)", "Set" if serp_key else "Not set")

    if not anthropic_key:
        st.markdown("")
        st.markdown(
            "**To add your Anthropic key:**\n\n"
            "1. Create `.streamlit/secrets.toml`\n"
            "2. Add: `ANTHROPIC_API_KEY = \"sk-ant-...\"`\n"
            "3. Restart the app"
        )

# ── Tab 3: Database ─────────────────────────────────────────────────────────
with tab_db:
    total = count_jobs()
    st.markdown(f"### Database  ·  {total:,} jobs")

    col_export, col_clear, col_reset = st.columns(3)

    with col_export:
        st.markdown("**Export**")
        if st.button("Export to CSV", use_container_width=True):
            jobs = get_jobs(limit=9999)
            if jobs:
                df = pd.DataFrame(jobs)
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name="fresher_jobs.csv",
                    mime="text/csv",
                )
            else:
                st.info("No jobs to export.")

    with col_clear:
        st.markdown("**Cleanup**")
        days_old = st.number_input("Older than (days)", value=30, min_value=1, step=1)
        if st.button("Delete old jobs", use_container_width=True):
            deleted = delete_old_jobs(int(days_old))
            st.success(f"Deleted {deleted} jobs.")

    with col_reset:
        st.markdown("**Reset analyses**")
        st.caption("Clear all AI match results. You can re-run from Resume Analyzer.")
        if st.button("Clear all analyses", use_container_width=True):
            from core.database import get_db
            with get_db() as conn:
                conn.execute("DELETE FROM analyses")
            st.success("All analyses cleared.")

# ── Tab 4: Scrape Log ───────────────────────────────────────────────────────
with tab_logs:
    st.markdown("### Recent scrape runs")

    logs = get_scrape_logs(limit=30)
    if logs:
        df = pd.DataFrame(logs)[[
            "portal", "started_at", "finished_at",
            "jobs_found", "jobs_new", "status", "error_message"
        ]]
        df["portal"] = df["portal"].str.title()
        df["started_at"] = df["started_at"].str[:19].str.replace("T", " ")
        df["finished_at"] = df["finished_at"].fillna("—").str[:19].str.replace("T", " ")
        df.columns = ["Portal", "Started (UTC)", "Finished (UTC)", "Found", "New", "Status", "Error"]

        def _color_status(val):
            if val == "success":
                return "background-color: #052e16; color: #4ade80"
            elif val in ("error", "SELECTOR_DRIFT"):
                return "background-color: #1c1017; color: #f87171"
            elif val == "partial":
                return "background-color: #1c1917; color: #fbbf24"
            elif val == "running":
                return "background-color: #0c1629; color: #60a5fa"
            return ""

        styled = df.style.map(_color_status, subset=["Status"])
        st.dataframe(styled, use_container_width=True, height=400)
    else:
        st.info("No scrape history yet. Trigger a scrape from the Scrapers tab.")
