"""Shared minimal CSS and UI helpers."""

import json

import streamlit as st


def inject_css():
    """Inject global CSS for a clean, minimal dark theme."""
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """<style>
/* ── Base reset ─────────────────────────────────────────── */
[data-testid="stAppViewContainer"] { padding-top: 0.5rem; }
[data-testid="stSidebar"] { background: #0c0c0f; border-right: 1px solid #1a1a2e; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: 0.9rem; }
section[data-testid="stSidebar"] > div { padding-top: 1.5rem; }

/* ── Typography ─────────────────────────────────────────── */
h1 { font-size: 1.75rem !important; font-weight: 600 !important;
     letter-spacing: -0.03em; margin-bottom: 0.25rem !important; }
h2 { font-size: 1.2rem !important; font-weight: 500 !important;
     color: #a1a1aa !important; margin-top: 1.5rem !important; }
h3 { font-size: 1rem !important; font-weight: 500 !important;
     color: #d4d4d8 !important; }

/* ── Metric cards ───────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #111118; border: 1px solid #1e1e2e; border-radius: 10px;
    padding: 16px 20px; transition: border-color 0.2s;
}
[data-testid="stMetric"]:hover { border-color: #6366f1; }
[data-testid="stMetric"] label { font-size: 0.75rem !important;
    color: #71717a !important; text-transform: uppercase; letter-spacing: 0.05em; }
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.6rem !important; font-weight: 600 !important; }

/* ── Buttons ────────────────────────────────────────────── */
.stButton > button {
    border-radius: 8px; font-weight: 500; font-size: 0.85rem;
    padding: 0.45rem 1.2rem; transition: all 0.2s;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: #6366f1; border: none;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: #4f46e5; box-shadow: 0 0 20px rgba(99,102,241,0.25);
}
.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"] {
    background: transparent; border: 1px solid #27272a;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="stBaseButton-secondary"]:hover {
    border-color: #6366f1; color: #a5b4fc;
}

/* ── Expander ───────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #111118; border: 1px solid #1e1e2e; border-radius: 10px;
    margin-bottom: 0.5rem; transition: border-color 0.2s;
}
[data-testid="stExpander"]:hover { border-color: #2d2d44; }
[data-testid="stExpander"] summary span {
    font-size: 0.9rem !important; font-weight: 500 !important; }

/* ── Tabs ───────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0; border-bottom: 1px solid #1e1e2e;
}
.stTabs [data-baseweb="tab"] {
    padding: 10px 24px; font-size: 0.85rem; font-weight: 500;
    color: #71717a; border-bottom: 2px solid transparent;
    transition: all 0.2s;
}
.stTabs [aria-selected="true"] {
    color: #e4e4e7 !important;
    border-bottom: 2px solid #6366f1 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #a1a1aa; }

/* ── Forms & inputs ─────────────────────────────────────── */
[data-testid="stForm"] {
    background: #111118; border: 1px solid #1e1e2e; border-radius: 10px;
    padding: 1.5rem;
}
input, textarea, [data-baseweb="select"] {
    border-radius: 8px !important;
}

/* ── Dataframes ─────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #1e1e2e; border-radius: 10px; overflow: hidden;
}

/* ── Dividers ───────────────────────────────────────────── */
hr { border-color: #1a1a2e !important; margin: 1.5rem 0 !important; }

/* ── Progress bar ───────────────────────────────────────── */
.stProgress > div > div { background: #6366f1 !important; border-radius: 99px; }

/* ── Custom job card ────────────────────────────────────── */
.job-card-wrapper {
    background: #111118; border: 1px solid #1e1e2e; border-radius: 10px;
    padding: 1rem 1.25rem; margin-bottom: 0.6rem;
    transition: border-color 0.2s, transform 0.15s;
}
.job-card-wrapper:hover { border-color: #6366f1; transform: translateY(-1px); }
.job-card-title { font-size: 0.95rem; font-weight: 600; color: #f4f4f5;
    margin: 0 0 4px; }
.job-card-company { font-size: 0.82rem; color: #a1a1aa; margin: 0 0 6px; }
.job-card-meta { font-size: 0.75rem; color: #71717a; margin: 0; }
.job-card-meta span { margin-right: 12px; }
.score-pill {
    display: inline-block; padding: 2px 10px; border-radius: 99px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em;
}
.score-high   { background: #052e16; color: #4ade80; border: 1px solid #166534; }
.score-mid    { background: #1c1917; color: #fbbf24; border: 1px solid #854d0e; }
.score-low    { background: #1c1017; color: #f87171; border: 1px solid #991b1b; }

/* ── Nav card (home) ────────────────────────────────────── */
.nav-card {
    background: #111118; border: 1px solid #1e1e2e; border-radius: 12px;
    padding: 1.5rem; height: 100%; transition: all 0.2s;
    cursor: pointer;
}
.nav-card:hover { border-color: #6366f1; transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(99,102,241,0.08); }
.nav-card h3 { margin: 0 0 6px !important; font-size: 1rem !important;
    color: #e4e4e7 !important; font-weight: 600 !important; }
.nav-card p { font-size: 0.82rem; color: #71717a; margin: 0; line-height: 1.5; }

/* ── Status badges ──────────────────────────────────────── */
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 6px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em;
}
.badge-success { background: #052e16; color: #4ade80; }
.badge-error   { background: #1c1017; color: #f87171; }
.badge-warn    { background: #1c1917; color: #fbbf24; }
.badge-info    { background: #0c1629; color: #60a5fa; }

/* ── Subtle info blocks ─────────────────────────────────── */
[data-testid="stAlert"] { border-radius: 10px; }

/* ── Slider ─────────────────────────────────────────────── */
[data-testid="stSlider"] [role="slider"] {
    background: #6366f1 !important;
}

/* ── Toggle ─────────────────────────────────────────────── */
[data-testid="stToggle"] label span {
    font-size: 0.85rem;
}

/* ── Scrollbar ──────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #27272a; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #3f3f46; }

/* ── Sidebar nav ────────────────────────────────────────── */
[data-testid="stSidebarNavItems"] a {
    font-size: 0.88rem !important; padding: 0.5rem 1rem !important;
    border-radius: 8px; transition: background 0.15s;
}
[data-testid="stSidebarNavItems"] a:hover { background: #1a1a2e; }
[data-testid="stSidebarNavItems"] a[aria-current="page"] {
    background: #1a1a2e; border-left: 2px solid #6366f1;
}

/* ── Relevance reason text ─────────────────────────────────── */
.relevance-reason {
    font-size: 0.75rem; color: #818cf8; margin: 4px 0 8px;
}
</style>"""


def score_pill(score) -> str:
    """Return HTML for a colored score pill."""
    if score is None:
        return ""
    s = float(score)
    if s >= 70:
        cls = "score-high"
    elif s >= 50:
        cls = "score-mid"
    else:
        cls = "score-low"
    return f'<span class="score-pill {cls}">{s:.0f}%</span>'


def badge(text: str, variant: str = "info") -> str:
    """Return HTML for a status badge. Variants: success, error, warn, info."""
    return f'<span class="badge badge-{variant}">{text}</span>'


def parse_json_list(val) -> list:
    """Parse a value that may be a JSON string, a list, or None into a list."""
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except Exception:
        return []


def color_score_cell(val: str) -> str:
    """Pandas Styler function: return CSS for a score cell like '72%'."""
    try:
        n = int(val.replace("%", ""))
        if n >= 70:
            return "background-color: #052e16; color: #4ade80"
        elif n >= 50:
            return "background-color: #1c1917; color: #fbbf24"
        else:
            return "background-color: #1c1017; color: #f87171"
    except Exception:
        return ""
