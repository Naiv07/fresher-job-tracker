"""Resume Analyzer — upload, analyze, and view skill gaps."""

import pandas as pd
import streamlit as st

from ai.matcher import analyze_all_jobs, get_top_missing_skills
from ai.resume_parser import parse_resume
from core.database import (
    count_jobs,
    get_active_resume,
    get_analysis_stats,
    get_jobs,
    save_resume,
)
from styles import inject_css, score_pill, parse_json_list, color_score_cell

st.set_page_config(page_title="Resume Analyzer", layout="wide")
inject_css()

st.title("Resume Analyzer")
st.caption("Upload your resume and get AI-powered match scores")

# ── Fetch resume once for all tabs ───────────────────────────────────────────
current_resume = get_active_resume()

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_upload, tab_results, tab_skills = st.tabs(["Upload", "Results", "Skills Gap"])

# ── Tab 1: Upload ────────────────────────────────────────────────────────────
with tab_upload:
    if current_resume:
        st.markdown(
            f"**Active resume:** {current_resume['filename']}  ·  "
            f"Uploaded {current_resume['upload_at'][:10]}"
        )
        replace = st.checkbox("Upload a different resume")
    else:
        replace = True

    if replace or not current_resume:
        uploaded = st.file_uploader(
            "Upload resume (PDF or DOCX)",
            type=["pdf", "docx"],
            help="Your resume text is stored locally and used only for job matching.",
        )

        if uploaded:
            with st.spinner("Parsing..."):
                try:
                    text = parse_resume(uploaded.read(), uploaded.name)
                    save_resume(uploaded.name, text)
                    current_resume = get_active_resume()
                    st.success(f"Uploaded: **{uploaded.name}** ({len(text):,} characters)")
                    with st.expander("Preview extracted text"):
                        st.text_area("", text[:1000], height=200, disabled=True)
                except Exception as e:
                    st.error(f"Could not parse: {e}")

    if not current_resume:
        st.info("Upload your resume to enable AI analysis.")
    else:
        resume_id = current_resume["id"]
        resume_text = current_resume["raw_text"]

        # ── Run analysis ─────────────────────────────────────────────────────
        st.markdown("")
        st.markdown("### Run analysis")

        stats = get_analysis_stats(resume_id)
        total_analyzed = stats.get("total", 0) or 0
        avg_score = stats.get("avg_score")
        above_70 = stats.get("above_70", 0) or 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Analyzed", f"{total_analyzed:,}")
        c2.metric("Avg Match", f"{avg_score:.0f}%" if avg_score else "—")
        c3.metric("Strong (70%+)", f"{above_70:,}")

        total_unanalyzed = count_jobs() - total_analyzed
        est_cost = total_unanalyzed * 0.001

        @st.fragment
        def _run_analysis(r_id, r_text, unanalyzed, cost):
            st.markdown("")
            col_all, col_50 = st.columns(2)

            with col_all:
                btn_all = st.button(
                    f"Analyze all ({unanalyzed:,} remaining)",
                    type="primary",
                    disabled=unanalyzed == 0,
                    use_container_width=True,
                )
                if unanalyzed > 0:
                    st.caption(f"Est. cost: ~${cost:.2f} (Haiku)")

            with col_50:
                btn_50 = st.button(
                    "Analyze top 50",
                    disabled=unanalyzed == 0,
                    use_container_width=True,
                )

            if btn_all or btn_50:
                limit = 9999 if btn_all else 50
                progress_bar = st.progress(0.0, text="Starting...")
                status_text = st.empty()

                def _progress(current, total, job_title):
                    pct = current / total if total > 0 else 0
                    progress_bar.progress(pct, text=f"Analyzing {current}/{total}")
                    status_text.caption(f"{job_title[:60]}  ·  ~{int((total - current) * 1.5)}s left")

                with st.spinner("Running AI analysis..."):
                    summary = analyze_all_jobs(
                        resume_id=r_id,
                        resume_text=r_text,
                        limit=limit,
                        progress_callback=_progress,
                    )

                progress_bar.progress(1.0, text="Done")
                status_text.empty()
                st.success(f"Done. Analyzed: **{summary['analyzed']}**  ·  Errors: **{summary['errors']}**")
                st.rerun(scope="app")

        _run_analysis(resume_id, resume_text, total_unanalyzed, est_cost)

# ── Tab 2: Results ───────────────────────────────────────────────────────────
with tab_results:
    if not current_resume:
        st.info("Upload a resume first.")
    else:
        resume_id = current_resume["id"]
        stats = get_analysis_stats(resume_id)
        total_analyzed = stats.get("total", 0) or 0

        if total_analyzed == 0:
            st.info("Run analysis on the Upload tab to see results.")
        else:
            jobs = get_jobs(sort="score", limit=100, resume_id=resume_id)

            rows = []
            for job in jobs:
                score = job.get("match_score")
                matched_list = parse_json_list(job.get("matched_skills"))
                missing_list = parse_json_list(job.get("missing_skills"))

                rows.append({
                    "Portal": (job.get("portal") or "").title(),
                    "Title": job.get("title", ""),
                    "Company": job.get("company", ""),
                    "Location": job.get("location", ""),
                    "Match": f"{score:.0f}%" if score is not None else "—",
                    "Matched Skills": ", ".join(matched_list[:5]),
                    "Missing Skills": ", ".join(missing_list[:5]),
                    "_apply": job.get("apply_url", ""),
                })

            if rows:
                df = pd.DataFrame(rows)
                display_df = df.drop(columns=["_apply"])
                styled = display_df.style.map(color_score_cell, subset=["Match"])
                st.dataframe(styled, use_container_width=True, height=450)

                st.markdown("")
                st.markdown("**Apply to a job**")
                selected_idx = st.number_input(
                    "Row number", min_value=0, max_value=len(rows) - 1, value=0, step=1
                )
                sel = rows[selected_idx]
                if sel["_apply"]:
                    st.markdown(f"**{sel['Title']}** at {sel['Company']}")
                    st.link_button("Apply", sel["_apply"], type="primary")

# ── Tab 3: Skills Gap ───────────────────────────────────────────────────────
with tab_skills:
    if not current_resume:
        st.info("Upload a resume first.")
    else:
        resume_id = current_resume["id"]
        stats = get_analysis_stats(resume_id)
        total_analyzed = stats.get("total", 0) or 0

        if total_analyzed == 0:
            st.info("Analyze jobs first to see the skills gap chart.")
        else:
            st.markdown("### What to learn next")
            st.caption("Most frequently missing skills across all analyzed jobs")

            top_skills = get_top_missing_skills(resume_id, top_n=15)
            if top_skills:
                import plotly.graph_objects as go

                labels = [s["skill"] for s in top_skills]
                counts = [s["count"] for s in top_skills]
                max_c = max(counts) if counts else 1

                fig = go.Figure(go.Bar(
                    x=counts,
                    y=labels,
                    orientation="h",
                    marker_color=[
                        "#6366f1" if c >= max_c * 0.6 else
                        "#818cf8" if c >= max_c * 0.3 else
                        "#312e81"
                        for c in counts
                    ],
                ))
                fig.update_layout(
                    xaxis_title="Jobs requiring this skill",
                    yaxis=dict(autorange="reversed"),
                    height=420,
                    margin=dict(l=0, r=0, t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a1a1aa", size=12),
                    xaxis=dict(gridcolor="#1e1e2e"),
                    yaxis_tickfont=dict(color="#d4d4d8"),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No skill gap data available yet.")
