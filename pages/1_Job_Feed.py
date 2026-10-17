"""Job Feed — browse, filter, and apply to fresher jobs."""

import html

import streamlit as st

from core.config import PORTALS, ROLE_SEARCH_TERMS
from core.database import (
    count_jobs, get_active_resume, get_bookmarked_job_ids, get_jobs,
    get_last_successful_scrape, is_bookmarked, log_interaction, log_search,
)
from core.preferences import compute_relevance_scores, recompute_preferences
from core.database import get_all_preferences
from core.scheduler import is_data_stale, run_scrape_in_background
from styles import inject_css, score_pill, parse_json_list

st.set_page_config(page_title="Job Feed", layout="wide")
inject_css()

st.title("Job Feed")
st.caption("Browse and filter fresher jobs from all portals")

# ── Sidebar filters ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")

    selected_portals = st.multiselect(
        "Portals",
        options=PORTALS,
        default=PORTALS,
        format_func=lambda x: x.title(),
    )

    role_options = list(ROLE_SEARCH_TERMS.keys())
    selected_roles = st.multiselect(
        "Roles",
        options=role_options,
        default=role_options,
    )

    date_range = st.selectbox(
        "Posted within",
        options=["All time", "Today", "3 days", "7 days", "14 days"],
        index=3,
    )
    days_map = {"All time": None, "Today": 1, "3 days": 3, "7 days": 7, "14 days": 14}
    days = days_map[date_range]

    keyword = st.text_input("Search", placeholder="SQL, Power BI, Python...")

    sort_by = st.selectbox(
        "Sort",
        options=["Recommended", "Newest", "Best match", "Company A-Z"],
        index=0,
    )
    sort_map = {"Newest": "newest", "Best match": "score", "Company A-Z": "company", "Recommended": "newest"}

    has_resume = get_active_resume() is not None
    min_score_filter = 0.0
    if has_resume:
        min_score_filter = st.slider("Min match %", 0, 100, 0, 5, format="%d%%")
    else:
        st.caption("Upload a resume to filter by match score.")

    show_bookmarked = st.checkbox("Show saved only")

# ── Build query params ───────────────────────────────────────────────────────
resume = get_active_resume()
resume_id = resume["id"] if resume else None

role_terms: list[str] = []
for role in selected_roles:
    role_terms.extend(ROLE_SEARCH_TERMS.get(role, [role]))

total = count_jobs(
    portals=selected_portals or None,
    roles_like=role_terms or None,
    days=days,
    keyword=keyword or None,
)

# ── Header bar ───────────────────────────────────────────────────────────────
last_scraped = get_last_successful_scrape()
last_label = (
    f"Last scraped {last_scraped[:16].replace('T', ' ')} UTC"
    if last_scraped else "Never scraped"
)

col_info, col_btn = st.columns([5, 1])
with col_info:
    st.markdown(f"**{total:,} jobs**  ·  {last_label}")
with col_btn:
    if st.button("Scrape now", use_container_width=True):
        run_scrape_in_background()
        st.toast("Scrape started in background.")

if is_data_stale() and last_scraped:
    st.warning("Data may be stale. Click **Scrape now** to refresh.")

# ── Log search (deduplicated) ───────────────────────────────────────────────
search_sig = f"{keyword}|{selected_roles}|{selected_portals}|{min_score_filter}|{sort_by}"
if st.session_state.get("last_search_sig") != search_sig:
    log_search(keyword, selected_roles, selected_portals, min_score_filter, sort_by)
    st.session_state["last_search_sig"] = search_sig

# ── Throttled preference recomputation ──────────────────────────────────────
if resume_id:
    import time
    last_recomp = st.session_state.get("prefs_last_recomputed", 0)
    if time.time() - last_recomp > 600:  # every 10 min
        recompute_preferences(resume_id)
        st.session_state["prefs_last_recomputed"] = time.time()

# ── Pagination ───────────────────────────────────────────────────────────────
PAGE_SIZE = 20
if "job_page" not in st.session_state:
    st.session_state.job_page = 0

total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

# ── Fetch jobs ───────────────────────────────────────────────────────────────
# For Recommended sort, fetch more jobs so re-ranking has a meaningful pool
fetch_limit = 100 if sort_by == "Recommended" else PAGE_SIZE
fetch_offset = 0 if sort_by == "Recommended" else st.session_state.job_page * PAGE_SIZE

jobs = get_jobs(
    portals=selected_portals or None,
    roles_like=role_terms or None,
    min_score=float(min_score_filter) if min_score_filter > 0 else None,
    keyword=keyword or None,
    days=days,
    sort=sort_map[sort_by],
    limit=fetch_limit,
    offset=fetch_offset,
    resume_id=resume_id,
)

# ── Filter bookmarked only ──────────────────────────────────────────────────
if show_bookmarked:
    bookmarked_ids = set(get_bookmarked_job_ids())
    jobs = [j for j in jobs if j["id"] in bookmarked_ids]

# ── Apply relevance scoring ─────────────────────────────────────────────────
preferences = get_all_preferences()
if sort_by == "Recommended" and preferences:
    jobs = compute_relevance_scores(jobs, preferences)
    # Paginate after re-ranking
    start = st.session_state.job_page * PAGE_SIZE
    jobs = jobs[start : start + PAGE_SIZE]
    total_pages = max(1, (min(total, 100) + PAGE_SIZE - 1) // PAGE_SIZE)
elif sort_by == "Recommended":
    # No preferences yet — still compute for display but don't re-rank
    if jobs:
        compute_relevance_scores(jobs, preferences)
        start = st.session_state.job_page * PAGE_SIZE
        jobs = jobs[start : start + PAGE_SIZE]
        total_pages = max(1, (min(total, 100) + PAGE_SIZE - 1) // PAGE_SIZE)

if not jobs:
    st.markdown("")
    st.info("No jobs found. Adjust filters or click **Scrape now** to fetch fresh jobs.")
else:
    if sort_by == "Recommended" and preferences:
        st.caption("Personalized for you — based on your resume, searches, and feedback")
    st.markdown("")

    for job in jobs:
        score = job.get("match_score")
        portal_label = (job.get("portal") or "").title()
        posted = (job.get("posted_date") or job.get("scraped_at", ""))[:10]

        # Card header
        pill = score_pill(score)
        header = f"**{job['title']}**  —  {job['company']}"
        if pill:
            header += f"  {pill}"

        with st.expander(f"[{portal_label}]  {job['title']}  —  {job['company']}  ·  {posted}", expanded=False):
            col_main, col_side = st.columns([3, 1])

            with col_main:
                # Score pill
                if score is not None:
                    st.markdown(score_pill(score), unsafe_allow_html=True)

                # Relevance reasons
                reasons = job.get("relevance_reasons", [])
                if reasons and sort_by == "Recommended":
                    st.markdown(
                        f"<div style='font-size:0.75rem;color:#818cf8;margin:4px 0 8px'>"
                        f"{'  ·  '.join(reasons)}</div>",
                        unsafe_allow_html=True,
                    )

                # Meta
                meta = []
                if job.get("location"):
                    meta.append(job["location"])
                if job.get("salary_range"):
                    meta.append(job["salary_range"])
                exp_min = job.get("experience_min", 0) or 0
                exp_max = job.get("experience_max", 2) or 2
                meta.append(f"{exp_min}-{exp_max} yrs")
                meta.append(portal_label)
                if job.get("relevance_score") and sort_by == "Recommended":
                    meta.append(f"Relevance: {job['relevance_score']:.0f}")
                st.caption("  ·  ".join(meta))

                # Company description
                if job.get("company_desc"):
                    desc = job["company_desc"]
                    st.markdown(
                        f"**About {job['company']}:** {desc[:250]}{'...' if len(desc) > 250 else ''}"
                    )

                # JD
                jd = job.get("full_jd", "") or ""
                if jd:
                    st.markdown("**Job Description**")
                    jd_safe = html.escape(jd[:2500])
                    st.markdown(
                        f"<div style='max-height:250px;overflow-y:auto;font-size:0.82rem;"
                        f"color:#a1a1aa;line-height:1.6;white-space:pre-wrap'>{jd_safe}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("No description available.")

            with col_side:
                # Apply button (tracked)
                @st.fragment
                def _apply_btn(j=job):
                    if j.get("apply_url"):
                        if st.button("Apply", key=f"apply_{j['id']}", type="primary", use_container_width=True):
                            log_interaction(j["id"], "apply_click")
                            st.session_state[f"show_link_{j['id']}"] = True
                        if st.session_state.get(f"show_link_{j['id']}"):
                            st.link_button("Open listing", j["apply_url"], use_container_width=True)
                _apply_btn()

                # Bookmark + feedback row
                @st.fragment
                def _actions(j=job):
                    col_bm, col_up, col_dn = st.columns(3)
                    with col_bm:
                        bm = is_bookmarked(j["id"])
                        if st.button("Saved" if bm else "Save", key=f"bm_{j['id']}",
                                     use_container_width=True):
                            log_interaction(j["id"], "unbookmark" if bm else "bookmark")
                            st.rerun(scope="app")
                    with col_up:
                        if st.button("+", key=f"up_{j['id']}", help="Good match",
                                     use_container_width=True):
                            log_interaction(j["id"], "thumbs_up")
                            if resume_id:
                                recompute_preferences(resume_id)
                                st.session_state["prefs_last_recomputed"] = __import__("time").time()
                            st.toast("Noted — more like this")
                    with col_dn:
                        if st.button("-", key=f"dn_{j['id']}", help="Not for me",
                                     use_container_width=True):
                            log_interaction(j["id"], "thumbs_down")
                            if resume_id:
                                recompute_preferences(resume_id)
                                st.session_state["prefs_last_recomputed"] = __import__("time").time()
                            st.toast("Noted — fewer like this")
                _actions()

                # Skills
                matched = parse_json_list(job.get("matched_skills"))
                missing = parse_json_list(job.get("missing_skills"))
                tips    = parse_json_list(job.get("improvement_tips"))

                if matched:
                    st.markdown("**Matched**")
                    st.markdown(" ".join(f"`{s}`" for s in matched[:6]))

                if missing:
                    st.markdown("**Missing**")
                    st.markdown(" ".join(f"`{s}`" for s in missing[:6]))

                if tips:
                    st.markdown("**Tips**")
                    for tip in tips[:3]:
                        st.caption(f"- {tip}")

                # Single-job analyze button
                if score is None and resume_id:
                    @st.fragment
                    def _do_analyze(j=job, r_id=resume_id):
                        if st.button("Analyze", key=f"a_{j['id']}", use_container_width=True):
                            from ai.matcher import analyze_job
                            from core.database import save_analysis
                            res = get_active_resume()
                            if res:
                                with st.spinner("Analyzing..."):
                                    result = analyze_job(res["raw_text"], j)
                                    save_analysis(res["id"], j["id"], result)
                                st.rerun(scope="app")
                    _do_analyze()

    # ── Pagination controls ──────────────────────────────────────────────────
    @st.fragment
    def _pagination(tp: int):
        if tp <= 1:
            return
        st.markdown("")
        col_prev, col_page, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("Prev", disabled=st.session_state.job_page == 0):
                st.session_state.job_page = max(0, st.session_state.job_page - 1)
                st.rerun(scope="app")
        with col_page:
            st.markdown(
                f"<div style='text-align:center;color:#71717a;font-size:0.85rem'>"
                f"Page {st.session_state.job_page + 1} of {tp}</div>",
                unsafe_allow_html=True,
            )
        with col_next:
            if st.button("Next", disabled=st.session_state.job_page >= tp - 1):
                st.session_state.job_page = min(tp - 1, st.session_state.job_page + 1)
                st.rerun(scope="app")

    _pagination(total_pages)
