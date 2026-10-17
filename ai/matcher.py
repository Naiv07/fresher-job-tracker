"""Resume-job matching pipeline using Claude.

Produces:
  - match_score (0–100)
  - matched_skills (list)
  - missing_skills (list)
  - improvement_tips (list of 3-5 actionable strings)
  - summary (2-sentence plain-English assessment)
"""

import json
import time

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ai.claude_client import call_claude
from core.config import (
    ANALYSIS_SLEEP_SEC,
    CLAUDE_BATCH_MODEL,
    CLAUDE_DETAIL_MODEL,
    MAX_JD_CHARS,
    MAX_RESUME_CHARS,
)
from core.database import (
    get_active_resume,
    get_analysis,
    get_jobs_without_analysis,
    save_analysis,
)
from utils.text_cleaner import truncate

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a technical recruiter AI specializing in fresher and \
early-career roles in India. You analyze resumes against job descriptions for \
roles like Data Analyst, Business Intelligence Analyst, and Finance Analyst.

Always respond with ONLY valid JSON — no prose, no markdown fences, no explanations. \
The JSON must match exactly the schema requested."""

MATCH_PROMPT_TEMPLATE = """\
Analyze this resume against the job description and return a JSON object with \
EXACTLY these keys:

{{
  "match_score": <integer 0-100>,
  "matched_skills": [<skills present in BOTH resume and JD>],
  "missing_skills": [<skills in JD but NOT in resume>],
  "improvement_tips": [<3-5 specific, actionable tips to close skill gaps>],
  "summary": "<2-sentence plain-English assessment of fit>"
}}

Scoring rubric:
- 80-100: Strong match → apply immediately
- 60-79:  Good match → minor gaps to address
- 40-59:  Moderate match → significant skill gaps
- 0-39:   Weak match → major gaps

RESUME:
---
{resume_text}
---

JOB: {title} at {company}
---
{jd_text}
---

Return ONLY the JSON object."""


# ── Single-job analysis ───────────────────────────────────────────────────────

def analyze_job(
    resume_text: str,
    job: dict,
    model: str = CLAUDE_BATCH_MODEL,
) -> dict:
    """Run Claude analysis for one resume+job pair.

    Returns a normalized result dict with all 5 keys, even on failure.
    """
    jd_text = (job.get("full_jd") or "") + "\n" + (job.get("company_desc") or "")

    prompt = MATCH_PROMPT_TEMPLATE.format(
        resume_text=truncate(resume_text, MAX_RESUME_CHARS),
        title=job.get("title", ""),
        company=job.get("company", ""),
        jd_text=truncate(jd_text, MAX_JD_CHARS),
    )

    raw_response = ""
    for attempt in range(2):
        try:
            raw_response = call_claude(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt if attempt == 0 else prompt + "\n\nIMPORTANT: Return ONLY the JSON object.",
                model=model,
                max_tokens=1200,
                cache_system=True,
            )
            result = json.loads(raw_response)
            # Validate required keys
            result.setdefault("match_score", 0)
            result.setdefault("matched_skills", [])
            result.setdefault("missing_skills", [])
            result.setdefault("improvement_tips", [])
            result.setdefault("summary", "")
            return result
        except json.JSONDecodeError:
            if attempt == 0:
                continue
            # Both attempts failed — return safe default
            return _error_result(f"JSON parse error: {raw_response[:200]}")
        except Exception as e:
            return _error_result(str(e))

    return _error_result("Unknown error")


def _error_result(reason: str) -> dict:
    return {
        "match_score": 0,
        "matched_skills": [],
        "missing_skills": [],
        "improvement_tips": [f"Analysis failed: {reason}"],
        "summary": "Analysis could not be completed.",
    }


@retry(
    retry=retry_if_exception_type(anthropic.RateLimitError),
    wait=wait_exponential(multiplier=2, min=4, max=120),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _analyze_with_backoff(resume_text: str, job: dict) -> dict:
    """Analyze a single job with exponential backoff on rate limits."""
    return analyze_job(resume_text, job)


# ── Batch analysis ────────────────────────────────────────────────────────────

def analyze_all_jobs(
    resume_id: int,
    resume_text: str,
    limit: int = 200,
    progress_callback=None,
) -> dict:
    """Analyze all jobs not yet analyzed for this resume.

    Args:
        resume_id: active resume DB id
        resume_text: parsed resume text
        limit: max jobs to analyze in one run
        progress_callback: called with (current, total, job_title) each step

    Returns:
        Summary dict with analyzed, skipped, errors counts
    """
    jobs = get_jobs_without_analysis(resume_id, limit=limit)
    total = len(jobs)
    analyzed = 0
    errors = 0

    for i, job in enumerate(jobs):
        if progress_callback:
            progress_callback(i + 1, total, job.get("title", ""))

        # Double-check cache (another session might have analyzed it)
        existing = get_analysis(resume_id, job["id"])
        if existing:
            continue

        try:
            result = _analyze_with_backoff(resume_text, job)
            save_analysis(resume_id, job["id"], result)
            analyzed += 1
        except Exception:
            errors += 1

        time.sleep(ANALYSIS_SLEEP_SEC)

    return {
        "analyzed": analyzed,
        "skipped": total - analyzed - errors,
        "errors": errors,
        "total": total,
    }


# ── Missing skills aggregation ────────────────────────────────────────────────

def get_top_missing_skills(resume_id: int, top_n: int = 20) -> list[dict]:
    """Return the most frequently missing skills across all analyzed jobs."""
    from collections import Counter
    import json
    from core.database import get_db

    with get_db() as conn:
        rows = conn.execute(
            "SELECT missing_skills FROM analyses WHERE resume_id = ? AND missing_skills IS NOT NULL",
            [resume_id],
        ).fetchall()

    counter: Counter = Counter()
    for row in rows:
        try:
            skills = json.loads(row[0])
            for skill in skills:
                if skill:
                    counter[skill.strip()] += 1
        except Exception:
            pass

    return [{"skill": skill, "count": count} for skill, count in counter.most_common(top_n)]
