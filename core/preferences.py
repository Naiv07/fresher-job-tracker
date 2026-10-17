"""Preference engine — learns from user behavior and ranks jobs by relevance.

Gathers signals from four sources:
  1. Resume profile (matched skills from analyses)
  2. Explicit feedback (thumbs up/down)
  3. Behavioral signals (apply clicks, bookmarks)
  4. Search history (keywords, roles, portals)

Produces weighted preference vectors and a composite relevance score.
"""

import json
import math
from collections import defaultdict
from datetime import datetime, timezone

from core.config import ROLE_SEARCH_TERMS
from core.database import get_db, upsert_preference

# ── Signal weights ───────────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    "thumbs_up":      3.0,
    "thumbs_down":   -2.0,
    "apply_click":    2.0,
    "bookmark":       1.5,
    "unbookmark":    -0.5,
    "search_keyword": 1.0,
    "search_role":    0.8,
    "search_portal":  0.5,
    "resume_skill":   1.0,
}

# Default ranking weights (how much each factor matters in the final score)
DEFAULT_RANKING_WEIGHTS = {
    "match_score":      0.45,
    "skill_affinity":   0.20,
    "location_affinity": 0.10,
    "role_affinity":    0.10,
    "portal_affinity":  0.05,
    "company_affinity": 0.05,
    "feedback_signal":  0.05,
}

DECAY_HALF_LIFE_DAYS = 30


# ── Helpers ──────────────────────────────────────────────────────────────────

def _decay(age_days: float) -> float:
    """Exponential decay: 1.0 at day 0, 0.5 at half-life."""
    return math.exp(-age_days * math.log(2) / DECAY_HALF_LIFE_DAYS)


def _days_ago(iso_str: str) -> float:
    """Return how many days ago an ISO timestamp is."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    except Exception:
        return 0


def _match_role(title: str) -> str:
    """Match a job title to a role category from ROLE_SEARCH_TERMS."""
    title_lower = title.lower()
    for role, terms in ROLE_SEARCH_TERMS.items():
        for term in terms:
            if term in title_lower:
                return role
    return ""


def _parse_json_safe(val) -> list:
    """Parse JSON string or list into a list."""
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except Exception:
        return []


# ── Signal extraction ────────────────────────────────────────────────────────

def _extract_resume_skills(resume_id: int) -> dict[str, float]:
    """Extract skill weights from resume's analysis results."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT matched_skills FROM analyses WHERE resume_id = ? AND matched_skills IS NOT NULL",
            [resume_id],
        ).fetchall()

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for skill in _parse_json_safe(row[0]):
            s = skill.strip()
            if s:
                counts[s] += 1

    if not counts:
        return {}

    max_count = max(counts.values())
    return {
        skill: SIGNAL_WEIGHTS["resume_skill"] * count / max_count
        for skill, count in counts.items()
    }


def _extract_interaction_signals() -> dict[str, dict[str, float]]:
    """Extract preference signals from user interactions.

    Returns {category: {key: weighted_sum}}.
    """
    signals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    with get_db() as conn:
        rows = conn.execute("""
            SELECT ui.action, ui.created_at,
                   j.title, j.location, j.portal, j.company,
                   a.matched_skills, a.missing_skills
            FROM user_interactions ui
            JOIN jobs j ON j.id = ui.job_id
            LEFT JOIN analyses a ON a.job_id = ui.job_id
            ORDER BY ui.created_at DESC
        """).fetchall()

    for row in rows:
        action = row["action"]
        weight = SIGNAL_WEIGHTS.get(action, 0)
        if weight == 0:
            continue

        age = _days_ago(row["created_at"])
        signal = weight * _decay(age)

        # Location
        loc = (row["location"] or "").strip()
        if loc:
            # Extract primary city (before comma)
            city = loc.split(",")[0].strip()
            if city:
                signals["location"][city] += signal

        # Portal
        portal = (row["portal"] or "").strip()
        if portal:
            signals["portal"][portal] += signal

        # Company
        company = (row["company"] or "").strip()
        if company:
            signals["company"][company] += signal

        # Role
        role = _match_role(row["title"] or "")
        if role:
            signals["role"][role] += signal

        # Skills (from analysis if available)
        all_skills = _parse_json_safe(row["matched_skills"]) + _parse_json_safe(row["missing_skills"])
        for skill in all_skills:
            s = skill.strip()
            if s:
                signals["skill"][s] += signal

    return dict(signals)


def _extract_search_signals() -> dict[str, dict[str, float]]:
    """Extract preference signals from search history."""
    signals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    with get_db() as conn:
        rows = conn.execute(
            "SELECT keyword, roles, portals, created_at FROM search_history ORDER BY created_at DESC"
        ).fetchall()

    for row in rows:
        age = _days_ago(row["created_at"])
        decay = _decay(age)

        # Keywords → skill preferences
        kw = (row["keyword"] or "").strip()
        if kw:
            for token in kw.split():
                token = token.strip().lower()
                if len(token) > 1:
                    signals["skill"][token] += SIGNAL_WEIGHTS["search_keyword"] * decay

        # Roles
        for role in _parse_json_safe(row["roles"]):
            signals["role"][role] += SIGNAL_WEIGHTS["search_role"] * decay

        # Portals
        for portal in _parse_json_safe(row["portals"]):
            signals["portal"][portal] += SIGNAL_WEIGHTS["search_portal"] * decay

    return dict(signals)


# ── Preference computation ───────────────────────────────────────────────────

def _normalize_signals(signals: dict[str, float]) -> dict[str, float]:
    """Normalize signal values to 0-10 scale. Clamp negatives to 0."""
    if not signals:
        return {}
    max_val = max(abs(v) for v in signals.values()) or 1.0
    return {
        k: max(0.0, min(10.0, (v / max_val) * 10.0))
        for k, v in signals.items()
    }


def recompute_preferences(resume_id: int) -> int:
    """Recompute all learned preferences from interaction data and resume.

    Returns the number of preference entries written.
    """
    # Gather signals from all sources
    resume_skills = _extract_resume_skills(resume_id)
    interaction_signals = _extract_interaction_signals()
    search_signals = _extract_search_signals()

    # Merge all signals by category
    merged: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    # Resume skills
    for skill, weight in resume_skills.items():
        merged["skill"][skill] += weight

    # Interaction signals
    for category, kv in interaction_signals.items():
        for key, weight in kv.items():
            merged[category][key] += weight

    # Search signals
    for category, kv in search_signals.items():
        for key, weight in kv.items():
            merged[category][key] += weight

    # Normalize and save
    count = 0
    for category, kv in merged.items():
        normalized = _normalize_signals(kv)
        for key, weight in normalized.items():
            if weight > 0.1:  # skip near-zero preferences
                upsert_preference(category, key, weight, source="learned")
                count += 1

    return count


# ── Relevance scoring ────────────────────────────────────────────────────────

def _get_ranking_weights(preferences: dict) -> dict[str, float]:
    """Get ranking weights, using manual overrides if set."""
    weights = dict(DEFAULT_RANKING_WEIGHTS)
    custom = preferences.get("_ranking_weight", {})
    for k, v in custom.items():
        if k in weights:
            weights[k] = v
    return weights


def _score_affinity(job_values: list[str], pref_map: dict[str, float]) -> float:
    """Compute affinity score (0-100) between job values and preference map."""
    if not job_values or not pref_map:
        return 50.0  # neutral
    max_weight = max(pref_map.values()) or 1.0
    matched = [pref_map.get(v, 0) for v in job_values if v in pref_map]
    if not matched:
        return 50.0
    return min(100.0, (sum(matched) / len(matched) / max_weight) * 100.0)


def compute_relevance_scores(
    jobs: list[dict],
    preferences: dict[str, dict[str, float]],
) -> list[dict]:
    """Add 'relevance_score' and 'relevance_reasons' to each job dict.

    Returns the same list sorted by relevance_score descending.
    """
    weights = _get_ranking_weights(preferences)
    skill_prefs = preferences.get("skill", {})
    loc_prefs = preferences.get("location", {})
    role_prefs = preferences.get("role", {})
    portal_prefs = preferences.get("portal", {})
    company_prefs = preferences.get("company", {})

    # Preload feedback signals for all job IDs
    job_ids = [j["id"] for j in jobs]
    feedback_map: dict[int, str] = {}
    if job_ids:
        with get_db() as conn:
            placeholders = ",".join("?" * len(job_ids))
            rows = conn.execute(
                f"SELECT job_id, action FROM user_interactions "
                f"WHERE job_id IN ({placeholders}) AND action IN ('thumbs_up', 'thumbs_down') "
                f"ORDER BY created_at ASC",
                job_ids,
            ).fetchall()
        for row in rows:
            feedback_map[row["job_id"]] = row["action"]  # last action wins

    for job in jobs:
        reasons = []

        # 1. Match score (from Claude analysis)
        match = job.get("match_score")
        match_norm = float(match) if match is not None else 50.0

        # 2. Skill affinity
        job_skills = (
            _parse_json_safe(job.get("matched_skills"))
            + _parse_json_safe(job.get("missing_skills"))
        )
        job_skills_clean = [s.strip() for s in job_skills if s and s.strip()]
        skill_score = _score_affinity(job_skills_clean, skill_prefs)
        if skill_score > 60 and skill_prefs:
            top_matched = [s for s in job_skills_clean if s in skill_prefs][:3]
            if top_matched:
                reasons.append(f"Skills: {', '.join(top_matched)}")

        # 3. Location affinity
        loc = (job.get("location") or "").strip()
        loc_city = loc.split(",")[0].strip() if loc else ""
        loc_score = 50.0
        if loc_city and loc_prefs:
            loc_score = _score_affinity([loc_city], loc_prefs)
            if loc_score > 60:
                reasons.append(f"Preferred location: {loc_city}")

        # 4. Role affinity
        role = _match_role(job.get("title", ""))
        role_score = 50.0
        if role and role_prefs:
            role_score = _score_affinity([role], role_prefs)
            if role_score > 60:
                reasons.append(f"Preferred role: {role}")

        # 5. Portal affinity
        portal = (job.get("portal") or "").strip()
        portal_score = _score_affinity([portal], portal_prefs) if portal else 50.0

        # 6. Company affinity
        company = (job.get("company") or "").strip()
        company_score = _score_affinity([company], company_prefs) if company else 50.0
        if company_score > 70 and company_prefs:
            reasons.append(f"Preferred company: {company}")

        # 7. Feedback signal
        fb = feedback_map.get(job["id"])
        fb_score = 100.0 if fb == "thumbs_up" else (0.0 if fb == "thumbs_down" else 50.0)

        # Composite score
        relevance = (
            weights["match_score"] * match_norm
            + weights["skill_affinity"] * skill_score
            + weights["location_affinity"] * loc_score
            + weights["role_affinity"] * role_score
            + weights["portal_affinity"] * portal_score
            + weights["company_affinity"] * company_score
            + weights["feedback_signal"] * fb_score
        )

        job["relevance_score"] = round(relevance, 1)
        job["relevance_reasons"] = reasons

    jobs.sort(key=lambda j: j["relevance_score"], reverse=True)
    return jobs
