"""My Preferences — view and adjust what the system has learned."""

import streamlit as st

from core.database import (
    get_active_resume,
    get_all_preferences,
    get_interaction_stats,
    upsert_preference,
    delete_preferences_by_category,
)
from core.preferences import (
    DEFAULT_RANKING_WEIGHTS,
    recompute_preferences,
)
from styles import inject_css

st.set_page_config(page_title="My Preferences", layout="wide")
inject_css()

st.title("My Preferences")
st.caption("The system learns from your resume, searches, and feedback. You can adjust weights manually.")

resume = get_active_resume()

# ── Stats ────────────────────────────────────────────────────────────────────
stats = get_interaction_stats()
c1, c2, c3 = st.columns(3)
c1.metric("Interactions", f"{stats['interactions']:,}")
c2.metric("Searches", f"{stats['searches']:,}")
c3.metric("Days of Data", f"{stats['days']}")

if stats["interactions"] == 0 and stats["searches"] == 0:
    st.markdown("")
    st.info(
        "No learning data yet. Use the **Job Feed** to browse, save, and rate jobs. "
        "The system will learn your preferences over time."
    )

# ── Recompute / Reset controls ──────────────────────────────────────────────
st.markdown("")
col_recomp, col_reset = st.columns(2)
with col_recomp:
    if st.button("Recompute now", type="primary", use_container_width=True,
                 disabled=not resume):
        if resume:
            count = recompute_preferences(resume["id"])
            st.success(f"Recomputed {count} preference entries.")
            st.rerun()
with col_reset:
    if st.button("Reset all learned", use_container_width=True):
        delete_preferences_by_category(None)
        st.success("All learned preferences cleared.")
        st.rerun()

# ── Preference tabs ──────────────────────────────────────────────────────────
preferences = get_all_preferences()

tab_skills, tab_locs, tab_roles, tab_portals, tab_companies, tab_weights = st.tabs(
    ["Skills", "Locations", "Roles", "Portals", "Companies", "Ranking Weights"]
)


def _render_preference_tab(category: str, label: str):
    """Render a bar chart and manual adjustment for a preference category."""
    prefs = preferences.get(category, {})

    if not prefs:
        st.info(f"No {label.lower()} preferences learned yet.")
        return

    # Sort by weight descending
    sorted_prefs = sorted(prefs.items(), key=lambda x: x[1], reverse=True)[:20]
    labels = [p[0] for p in sorted_prefs]
    weights = [p[1] for p in sorted_prefs]

    import plotly.graph_objects as go

    max_w = max(weights) if weights else 1
    fig = go.Figure(go.Bar(
        x=weights,
        y=labels,
        orientation="h",
        marker_color=[
            "#6366f1" if w >= max_w * 0.6 else
            "#818cf8" if w >= max_w * 0.3 else
            "#312e81"
            for w in weights
        ],
    ))
    fig.update_layout(
        xaxis_title="Preference weight",
        yaxis=dict(autorange="reversed"),
        height=max(250, len(labels) * 28),
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#a1a1aa", size=12),
        xaxis=dict(gridcolor="#1e1e2e", range=[0, 10.5]),
        yaxis_tickfont=dict(color="#d4d4d8"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Manual adjustment
    with st.expander("Adjust manually"):
        for name, weight in sorted_prefs[:10]:
            new_w = st.slider(
                name, 0.0, 10.0, float(weight), 0.5,
                key=f"pref_{category}_{name}",
            )
            if abs(new_w - weight) > 0.01:
                upsert_preference(category, name, new_w, source="manual")

        # Add new preference
        new_key = st.text_input(f"Add {label.lower()}", key=f"add_{category}",
                                placeholder=f"e.g. {'Python' if category == 'skill' else 'Bangalore'}")
        if new_key:
            new_weight = st.slider(f"Weight for {new_key}", 0.0, 10.0, 5.0, 0.5,
                                   key=f"addw_{category}")
            if st.button(f"Save", key=f"addbtn_{category}"):
                upsert_preference(category, new_key.strip(), new_weight, source="manual")
                st.success(f"Added: {new_key.strip()}")
                st.rerun()

        if st.button(f"Reset {label.lower()} to learned", key=f"reset_{category}"):
            delete_preferences_by_category(category)
            if resume:
                recompute_preferences(resume["id"])
            st.success(f"Reset {label.lower()} preferences.")
            st.rerun()


with tab_skills:
    _render_preference_tab("skill", "Skills")

with tab_locs:
    _render_preference_tab("location", "Locations")

with tab_roles:
    _render_preference_tab("role", "Roles")

with tab_portals:
    _render_preference_tab("portal", "Portals")

with tab_companies:
    _render_preference_tab("company", "Companies")

# ── Ranking weights tab ──────────────────────────────────────────────────────
with tab_weights:
    st.markdown("### How much each factor matters")
    st.caption(
        "These weights control how the Recommended sort blends different signals. "
        "They should sum to roughly 1.0."
    )

    # Load custom weights or defaults
    custom_weights = preferences.get("_ranking_weight", {})
    current = {k: custom_weights.get(k, v) for k, v in DEFAULT_RANKING_WEIGHTS.items()}

    labels_map = {
        "match_score": "AI Match Score",
        "skill_affinity": "Skill Affinity",
        "location_affinity": "Location Affinity",
        "role_affinity": "Role Affinity",
        "portal_affinity": "Portal Affinity",
        "company_affinity": "Company Affinity",
        "feedback_signal": "Your Feedback",
    }

    new_weights = {}
    for key, default_val in DEFAULT_RANKING_WEIGHTS.items():
        label = labels_map.get(key, key)
        new_weights[key] = st.slider(
            label, 0.0, 1.0, float(current[key]), 0.05,
            key=f"rw_{key}",
        )

    total_w = sum(new_weights.values())
    if total_w > 0:
        st.caption(f"Total: {total_w:.2f}")

    if st.button("Save ranking weights", type="primary"):
        for key, val in new_weights.items():
            upsert_preference("_ranking_weight", key, val, source="manual")
        st.success("Ranking weights saved.")
        st.rerun()

    if st.button("Reset to defaults"):
        delete_preferences_by_category("_ranking_weight")
        st.success("Reset to default ranking weights.")
        st.rerun()
