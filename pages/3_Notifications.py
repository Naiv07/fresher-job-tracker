"""Notifications — configure email alerts for new job matches."""

import streamlit as st

from core.config import PORTALS, ROLE_SEARCH_TERMS
from core.database import get_notification_config, save_notification_config
from notifications.email_sender import notify_new_jobs, send_test_email
from styles import inject_css

st.set_page_config(page_title="Notifications", layout="wide")
inject_css()

st.title("Notifications")
st.caption("Get email alerts when new matching jobs are found")

# ── Load config ──────────────────────────────────────────────────────────────
cfg = get_notification_config() or {}

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_config, tab_test = st.tabs(["Settings", "Test"])

# ── Tab 1: Settings ──────────────────────────────────────────────────────────
with tab_config:
    with st.form("notification_settings"):
        st.markdown("### Email")
        col1, col2 = st.columns(2)

        with col1:
            email_to = st.text_input(
                "Send alerts to",
                value=cfg.get("email_to", ""),
                placeholder="you@gmail.com",
            )
            smtp_user = st.text_input(
                "Gmail sender address",
                value=cfg.get("smtp_user", ""),
                placeholder="sender@gmail.com",
            )

        with col2:
            smtp_host = st.text_input("SMTP host", value=cfg.get("smtp_host", "smtp.gmail.com"))
            smtp_port = st.number_input(
                "SMTP port", value=cfg.get("smtp_port", 587), min_value=1, max_value=65535
            )

        st.caption(
            "Gmail App Password must be in `.streamlit/secrets.toml` as `GMAIL_APP_PASSWORD`. "
            "It is never stored in the database."
        )

        st.markdown("")
        st.markdown("### Filters")

        min_score = st.slider(
            "Min match score",
            min_value=0, max_value=100,
            value=int(cfg.get("min_match_score", 0)),
            step=5, format="%d%%",
            help="Set to 0 to get alerts for all new jobs.",
        )

        frequency = st.radio(
            "Frequency",
            options=["immediate", "daily_digest"],
            format_func=lambda x: "After each scrape" if x == "immediate" else "Daily digest (8 AM IST)",
            index=0 if cfg.get("frequency", "immediate") == "immediate" else 1,
            horizontal=True,
        )

        col_r, col_p = st.columns(2)
        with col_r:
            roles_filter = st.multiselect(
                "Roles",
                options=list(ROLE_SEARCH_TERMS.keys()),
                default=cfg.get("roles_filter") or list(ROLE_SEARCH_TERMS.keys()),
            )
        with col_p:
            portals_filter = st.multiselect(
                "Portals",
                options=PORTALS,
                default=cfg.get("portals_filter") or PORTALS,
                format_func=lambda x: x.title(),
            )

        is_enabled = st.toggle("Enable notifications", value=bool(cfg.get("is_enabled", True)))

        submitted = st.form_submit_button("Save settings", type="primary")

    if submitted:
        save_notification_config({
            "email_to": email_to,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
            "min_match_score": float(min_score),
            "roles_filter": roles_filter,
            "portals_filter": portals_filter,
            "frequency": frequency,
            "is_enabled": 1 if is_enabled else 0,
        })
        st.success("Settings saved.")

# ── Tab 2: Test ──────────────────────────────────────────────────────────────
with tab_test:
    st.markdown("### Send a test")
    st.caption("Verify your email configuration is working.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Test email**")
        st.caption("Sends a single dummy job alert to your configured address.")
        if st.button("Send test email", use_container_width=True):
            with st.spinner("Sending..."):
                success, error = send_test_email()
            if success:
                st.success("Test email sent. Check your inbox.")
            else:
                st.error(f"Failed: {error}")

    with col2:
        st.markdown("**Notify now**")
        st.caption("Send alerts for all un-notified jobs immediately.")
        if st.button("Notify new jobs", use_container_width=True):
            from core.database import get_active_resume
            resume = get_active_resume()
            with st.spinner("Sending..."):
                result = notify_new_jobs(
                    resume_id=resume["id"] if resume else None,
                    min_score=float(cfg.get("min_match_score", 0)),
                )
            if result.get("sent", 0) > 0:
                st.success(f"Sent alerts for {result['sent']} jobs.")
            else:
                reason = result.get("reason", result.get("error", "unknown"))
                st.info(f"No alerts sent: {reason}")
