"""SQLite database connection, schema creation, and CRUD helpers.

SECURITY NOTE: SMTP passwords are NEVER stored in this database.
They are read exclusively from st.secrets at runtime.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

from core.config import DB_PATH


# ── Connection factory ────────────────────────────────────────────────────────

def _make_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # concurrent read/write safety
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a database connection and auto-commit/rollback."""
    conn = _make_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema creation ───────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id_hash     TEXT    UNIQUE NOT NULL,
    portal          TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    company         TEXT    NOT NULL,
    company_desc    TEXT,
    location        TEXT,
    experience_min  INTEGER,
    experience_max  INTEGER,
    salary_range    TEXT,
    full_jd         TEXT,
    apply_url       TEXT    NOT NULL,
    posted_date     TEXT,
    scraped_at      TEXT    NOT NULL,
    is_notified     INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_jobs_portal   ON jobs(portal);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped  ON jobs(scraped_at);
CREATE INDEX IF NOT EXISTS idx_jobs_notified ON jobs(is_notified);
CREATE INDEX IF NOT EXISTS idx_jobs_active   ON jobs(is_active);

CREATE TABLE IF NOT EXISTS resumes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT    NOT NULL,
    upload_at   TEXT    NOT NULL,
    raw_text    TEXT    NOT NULL,
    is_active   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS analyses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id        INTEGER NOT NULL REFERENCES resumes(id),
    job_id           INTEGER NOT NULL REFERENCES jobs(id),
    match_score      REAL    NOT NULL,
    matched_skills   TEXT,
    missing_skills   TEXT,
    improvement_tips TEXT,
    raw_response     TEXT,
    analyzed_at      TEXT    NOT NULL,
    UNIQUE(resume_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_analyses_resume ON analyses(resume_id);
CREATE INDEX IF NOT EXISTS idx_analyses_job    ON analyses(job_id);
CREATE INDEX IF NOT EXISTS idx_analyses_score  ON analyses(match_score);

CREATE TABLE IF NOT EXISTS notification_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email_to        TEXT    NOT NULL,
    smtp_host       TEXT    DEFAULT 'smtp.gmail.com',
    smtp_port       INTEGER DEFAULT 587,
    smtp_user       TEXT,
    min_match_score REAL    DEFAULT 0.0,
    roles_filter    TEXT,
    portals_filter  TEXT,
    frequency       TEXT    DEFAULT 'immediate',
    is_enabled      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    portal        TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    jobs_found    INTEGER DEFAULT 0,
    jobs_new      INTEGER DEFAULT 0,
    error_message TEXT,
    status        TEXT DEFAULT 'running',
    batch_id      TEXT
);

CREATE INDEX IF NOT EXISTS idx_scrape_log_portal ON scrape_log(portal);
CREATE INDEX IF NOT EXISTS idx_scrape_log_status ON scrape_log(status);
CREATE INDEX IF NOT EXISTS idx_scrape_log_batch  ON scrape_log(batch_id);

CREATE TABLE IF NOT EXISTS user_interactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER REFERENCES jobs(id),
    action      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interactions_job    ON user_interactions(job_id);
CREATE INDEX IF NOT EXISTS idx_interactions_action ON user_interactions(action);
CREATE INDEX IF NOT EXISTS idx_interactions_time   ON user_interactions(created_at);

CREATE TABLE IF NOT EXISTS search_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT,
    roles       TEXT,
    portals     TEXT,
    min_score   REAL,
    sort_by     TEXT,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_search_time ON search_history(created_at);

CREATE TABLE IF NOT EXISTS user_preferences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT    NOT NULL,
    key         TEXT    NOT NULL,
    weight      REAL    NOT NULL DEFAULT 1.0,
    source      TEXT    NOT NULL DEFAULT 'learned',
    updated_at  TEXT    NOT NULL,
    UNIQUE(category, key)
);

CREATE INDEX IF NOT EXISTS idx_prefs_category ON user_preferences(category);
"""


def init_db() -> None:
    """Create all tables and indexes if they don't exist."""
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        # Migrate existing DBs: add batch_id to scrape_log if table exists but column is missing
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scrape_log'"
        ).fetchone()
        if existing:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(scrape_log)").fetchall()]
            if "batch_id" not in cols:
                conn.execute("ALTER TABLE scrape_log ADD COLUMN batch_id TEXT")
        # Now create all tables and indexes (safe for fresh + migrated DBs)
        conn.executescript(SCHEMA_SQL)


# ── Jobs ──────────────────────────────────────────────────────────────────────

def insert_job(job: dict) -> bool:
    """Insert a job row; return True if inserted, False if duplicate."""
    sql = """
        INSERT OR IGNORE INTO jobs
            (job_id_hash, portal, title, company, company_desc,
             location, experience_min, experience_max, salary_range,
             full_jd, apply_url, posted_date, scraped_at)
        VALUES
            (:job_id_hash, :portal, :title, :company, :company_desc,
             :location, :experience_min, :experience_max, :salary_range,
             :full_jd, :apply_url, :posted_date, :scraped_at)
    """
    with get_db() as conn:
        cur = conn.execute(sql, job)
        return cur.rowcount > 0


def get_jobs(
    portals: Optional[list] = None,
    roles_like: Optional[list] = None,
    min_score: Optional[float] = None,
    keyword: Optional[str] = None,
    days: Optional[int] = None,
    sort: str = "newest",
    limit: int = 20,
    offset: int = 0,
    resume_id: Optional[int] = None,
) -> list[dict]:
    """Fetch jobs with optional filters. Returns list of dicts."""
    params: list = []
    where: list[str] = ["j.is_active = 1"]

    if portals:
        placeholders = ",".join("?" * len(portals))
        where.append(f"j.portal IN ({placeholders})")
        params.extend(portals)

    if roles_like:
        role_clauses = " OR ".join(["LOWER(j.title) LIKE ?" for _ in roles_like])
        where.append(f"({role_clauses})")
        params.extend(f"%{r.lower()}%" for r in roles_like)

    if keyword:
        where.append("(LOWER(j.title) LIKE ? OR LOWER(j.full_jd) LIKE ?)")
        params += [f"%{keyword.lower()}%", f"%{keyword.lower()}%"]

    if days:
        where.append("j.scraped_at >= datetime('now', ?)")
        params.append(f"-{days} days")

    if min_score is not None and resume_id is not None:
        where.append("COALESCE(a.match_score, 0) >= ?")
        params.append(min_score)

    where_clause = " AND ".join(where)

    order_map = {
        "newest":  "j.scraped_at DESC",
        "score":   "COALESCE(a.match_score, -1) DESC",
        "company": "j.company ASC",
    }
    order = order_map.get(sort, "j.scraped_at DESC")

    join_clause = ""
    join_params: list = []
    if resume_id is not None:
        join_clause = "LEFT JOIN analyses a ON a.job_id = j.id AND a.resume_id = ?"
        join_params = [resume_id]
    else:
        join_clause = "LEFT JOIN analyses a ON a.job_id = j.id"

    sql = f"""
        SELECT j.*, a.match_score, a.matched_skills, a.missing_skills, a.improvement_tips
        FROM jobs j
        {join_clause}
        WHERE {where_clause}
        ORDER BY {order}
        LIMIT ? OFFSET ?
    """
    all_params = join_params + params + [limit, offset]

    with get_db() as conn:
        rows = conn.execute(sql, all_params).fetchall()
        return [dict(r) for r in rows]


def count_jobs(
    portals: Optional[list] = None,
    roles_like: Optional[list] = None,
    days: Optional[int] = None,
    keyword: Optional[str] = None,
) -> int:
    params: list = []
    where: list[str] = ["is_active = 1"]

    if portals:
        placeholders = ",".join("?" * len(portals))
        where.append(f"portal IN ({placeholders})")
        params.extend(portals)
    if roles_like:
        role_clauses = " OR ".join(["LOWER(title) LIKE ?" for _ in roles_like])
        where.append(f"({role_clauses})")
        params.extend(f"%{r.lower()}%" for r in roles_like)
    if keyword:
        where.append("(LOWER(title) LIKE ? OR LOWER(full_jd) LIKE ?)")
        params += [f"%{keyword.lower()}%", f"%{keyword.lower()}%"]
    if days:
        where.append("scraped_at >= datetime('now', ?)")
        params.append(f"-{days} days")

    sql = f"SELECT COUNT(*) FROM jobs WHERE {' AND '.join(where)}"
    with get_db() as conn:
        return conn.execute(sql, params).fetchone()[0]


def get_unnotified_jobs(min_score: float = 0.0, resume_id: Optional[int] = None) -> list[dict]:
    if resume_id is not None:
        sql = """
            SELECT j.*, a.match_score, a.matched_skills, a.missing_skills
            FROM jobs j
            LEFT JOIN analyses a ON a.job_id = j.id AND a.resume_id = ?
            WHERE j.is_notified = 0 AND j.is_active = 1
              AND COALESCE(a.match_score, 0) >= ?
            ORDER BY j.scraped_at DESC
        """
        params = [resume_id, min_score]
    else:
        sql = "SELECT * FROM jobs WHERE is_notified = 0 AND is_active = 1 ORDER BY scraped_at DESC"
        params = []

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def mark_jobs_notified(job_ids: list[int]) -> None:
    if not job_ids:
        return
    placeholders = ",".join("?" * len(job_ids))
    with get_db() as conn:
        conn.execute(f"UPDATE jobs SET is_notified = 1 WHERE id IN ({placeholders})", job_ids)


def delete_old_jobs(days: int) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE scraped_at < datetime('now', ?) AND is_active = 1",
            [f"-{days} days"],
        )
        return cur.rowcount


# ── Resumes ───────────────────────────────────────────────────────────────────

def save_resume(filename: str, raw_text: str) -> int:
    """Deactivate previous resumes and save a new active one. Returns new resume id."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE resumes SET is_active = 0")
        cur = conn.execute(
            "INSERT INTO resumes (filename, upload_at, raw_text, is_active) VALUES (?, ?, ?, 1)",
            [filename, now, raw_text],
        )
        return cur.lastrowid


def get_active_resume() -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


# ── Analyses ──────────────────────────────────────────────────────────────────

def save_analysis(resume_id: int, job_id: int, result: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO analyses
                (resume_id, job_id, match_score, matched_skills, missing_skills,
                 improvement_tips, raw_response, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                resume_id,
                job_id,
                result.get("match_score", 0),
                json.dumps(result.get("matched_skills", [])),
                json.dumps(result.get("missing_skills", [])),
                json.dumps(result.get("improvement_tips", [])),
                json.dumps(result),
                now,
            ],
        )


def get_analysis(resume_id: int, job_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE resume_id = ? AND job_id = ?",
            [resume_id, job_id],
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("matched_skills", "missing_skills", "improvement_tips"):
            if d.get(key):
                d[key] = json.loads(d[key])
        return d


def get_jobs_without_analysis(resume_id: int, limit: int = 200) -> list[dict]:
    sql = """
        SELECT j.* FROM jobs j
        WHERE j.is_active = 1
          AND NOT EXISTS (
              SELECT 1 FROM analyses a
              WHERE a.job_id = j.id AND a.resume_id = ?
          )
        ORDER BY j.scraped_at DESC
        LIMIT ?
    """
    with get_db() as conn:
        rows = conn.execute(sql, [resume_id, limit]).fetchall()
        return [dict(r) for r in rows]


def get_analysis_stats(resume_id: int) -> dict:
    sql = """
        SELECT
            COUNT(*)                                    AS total,
            AVG(match_score)                            AS avg_score,
            SUM(CASE WHEN match_score >= 70 THEN 1 ELSE 0 END) AS above_70,
            SUM(CASE WHEN match_score >= 80 THEN 1 ELSE 0 END) AS above_80
        FROM analyses WHERE resume_id = ?
    """
    with get_db() as conn:
        row = conn.execute(sql, [resume_id]).fetchone()
        return dict(row) if row else {}


# ── Notification config ───────────────────────────────────────────────────────

def get_notification_config() -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM notification_config ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("roles_filter", "portals_filter"):
            if d.get(key):
                d[key] = json.loads(d[key])
        return d


def save_notification_config(cfg: dict) -> None:
    cfg = dict(cfg)
    for key in ("roles_filter", "portals_filter"):
        if isinstance(cfg.get(key), list):
            cfg[key] = json.dumps(cfg[key])

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM notification_config LIMIT 1"
        ).fetchone()
        if existing:
            fields = ", ".join(f"{k} = :{k}" for k in cfg if k != "id")
            cfg["_id"] = existing[0]
            conn.execute(f"UPDATE notification_config SET {fields} WHERE id = :_id", cfg)
        else:
            keys = ", ".join(cfg.keys())
            vals = ", ".join(f":{k}" for k in cfg.keys())
            conn.execute(f"INSERT INTO notification_config ({keys}) VALUES ({vals})", cfg)


# ── Scrape log ────────────────────────────────────────────────────────────────

def log_scrape_start(portal: str, batch_id: Optional[str] = None) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO scrape_log (portal, started_at, status, batch_id) VALUES (?, ?, 'running', ?)",
            [portal, now, batch_id],
        )
        return cur.lastrowid


def log_scrape_end(log_id: int, jobs_found: int, jobs_new: int,
                   status: str = "success", error: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """UPDATE scrape_log
               SET finished_at = ?, jobs_found = ?, jobs_new = ?, status = ?, error_message = ?
               WHERE id = ?""",
            [now, jobs_found, jobs_new, status, error, log_id],
        )


def get_scrape_logs(limit: int = 30) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM scrape_log ORDER BY started_at DESC LIMIT ?", [limit]
        ).fetchall()
        return [dict(r) for r in rows]


def get_last_successful_scrape() -> Optional[str]:
    """Return ISO timestamp of last successful scrape across all portals, or None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT MAX(finished_at) FROM scrape_log WHERE status = 'success'"
        ).fetchone()
        return row[0] if row else None


def insert_jobs_batch(jobs: list[dict]) -> int:
    """Batch-insert jobs using executemany. Returns count of new (non-duplicate) rows."""
    if not jobs:
        return 0
    sql = """
        INSERT OR IGNORE INTO jobs
            (job_id_hash, portal, title, company, company_desc,
             location, experience_min, experience_max, salary_range,
             full_jd, apply_url, posted_date, scraped_at)
        VALUES
            (:job_id_hash, :portal, :title, :company, :company_desc,
             :location, :experience_min, :experience_max, :salary_range,
             :full_jd, :apply_url, :posted_date, :scraped_at)
    """
    with get_db() as conn:
        before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.executemany(sql, jobs)
        after = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        return after - before


def get_active_scrape_progress() -> Optional[dict]:
    """Return progress of currently running scrape, or None if idle.

    Returns: {running: int, portals_done: int, portals_total: int,
              total_new: int, batch_id: str}
    """
    with get_db() as conn:
        # Find the batch_id of any running scrape
        running_row = conn.execute(
            "SELECT batch_id FROM scrape_log WHERE status = 'running' AND batch_id IS NOT NULL "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not running_row:
            return None

        batch_id = running_row[0]

        # Count portals in this batch
        stats = conn.execute("""
            SELECT
                COUNT(*)                                              AS portals_total,
                SUM(CASE WHEN status != 'running' THEN 1 ELSE 0 END) AS portals_done,
                SUM(CASE WHEN status = 'running'  THEN 1 ELSE 0 END) AS running,
                COALESCE(SUM(jobs_new), 0)                            AS total_new
            FROM scrape_log WHERE batch_id = ?
        """, [batch_id]).fetchone()

        return {
            "running": stats["running"],
            "portals_done": stats["portals_done"],
            "portals_total": stats["portals_total"],
            "total_new": stats["total_new"],
            "batch_id": batch_id,
        }


def get_current_scrape_details(batch_id: str) -> list[dict]:
    """Return per-portal status for a given scrape batch."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT portal, status, jobs_found, jobs_new, error_message, started_at, finished_at "
            "FROM scrape_log WHERE batch_id = ? ORDER BY started_at",
            [batch_id],
        ).fetchall()
        return [dict(r) for r in rows]


# ── User interactions ────────────────────────────────────────────────────────

def log_interaction(job_id: int, action: str) -> None:
    """Record a user interaction with a job."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO user_interactions (job_id, action, created_at) VALUES (?, ?, ?)",
            [job_id, action, now],
        )


def log_search(keyword: str, roles: list, portals: list,
               min_score: float, sort_by: str) -> None:
    """Record a search/filter session."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO search_history (keyword, roles, portals, min_score, sort_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [keyword or "", json.dumps(roles or []), json.dumps(portals or []),
             min_score, sort_by, now],
        )


def is_bookmarked(job_id: int) -> bool:
    """Check if a job is currently bookmarked."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT
                SUM(CASE WHEN action = 'bookmark' THEN 1 ELSE 0 END) -
                SUM(CASE WHEN action = 'unbookmark' THEN 1 ELSE 0 END) AS net
            FROM user_interactions WHERE job_id = ?
        """, [job_id]).fetchone()
        return (row[0] or 0) > 0


def get_bookmarked_job_ids() -> list[int]:
    """Return all currently bookmarked job IDs."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT job_id,
                SUM(CASE WHEN action = 'bookmark' THEN 1 ELSE 0 END) -
                SUM(CASE WHEN action = 'unbookmark' THEN 1 ELSE 0 END) AS net
            FROM user_interactions
            WHERE action IN ('bookmark', 'unbookmark')
            GROUP BY job_id
            HAVING net > 0
        """).fetchall()
        return [r[0] for r in rows]


# ── User preferences ────────────────────────────────────────────────────────

def get_all_preferences() -> dict:
    """Return all preferences grouped by category: {category: {key: weight}}."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT category, key, weight FROM user_preferences"
        ).fetchall()
    result: dict = {}
    for row in rows:
        result.setdefault(row["category"], {})[row["key"]] = row["weight"]
    return result


def upsert_preference(category: str, key: str, weight: float,
                      source: str = "learned") -> None:
    """Insert or update a single preference."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO user_preferences (category, key, weight, source, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(category, key) DO UPDATE SET
                   weight = excluded.weight,
                   source = excluded.source,
                   updated_at = excluded.updated_at""",
            [category, key, weight, source, now],
        )


def upsert_preferences_batch(entries: list[tuple]) -> None:
    """Batch upsert preferences. Each entry: (category, key, weight, source)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO user_preferences (category, key, weight, source, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(category, key) DO UPDATE SET
                   weight = excluded.weight,
                   source = excluded.source,
                   updated_at = excluded.updated_at""",
            [(c, k, w, s, now) for c, k, w, s in entries],
        )


def get_bookmark_status_batch(job_ids: list[int]) -> set[int]:
    """Return set of job IDs that are currently bookmarked."""
    if not job_ids:
        return set()
    with get_db() as conn:
        placeholders = ",".join("?" * len(job_ids))
        rows = conn.execute(f"""
            SELECT job_id,
                SUM(CASE WHEN action = 'bookmark' THEN 1 ELSE 0 END) -
                SUM(CASE WHEN action = 'unbookmark' THEN 1 ELSE 0 END) AS net
            FROM user_interactions
            WHERE job_id IN ({placeholders}) AND action IN ('bookmark', 'unbookmark')
            GROUP BY job_id
            HAVING net > 0
        """, job_ids).fetchall()
        return {r[0] for r in rows}


def delete_preferences_by_category(category: Optional[str] = None) -> None:
    """Delete preferences. If category is None, delete all learned preferences."""
    with get_db() as conn:
        if category:
            conn.execute(
                "DELETE FROM user_preferences WHERE category = ? AND source = 'learned'",
                [category],
            )
        else:
            conn.execute("DELETE FROM user_preferences WHERE source = 'learned'")


def get_interaction_stats() -> dict:
    """Return counts of interactions, searches, and days of data."""
    with get_db() as conn:
        interactions = conn.execute(
            "SELECT COUNT(*) FROM user_interactions"
        ).fetchone()[0]
        searches = conn.execute(
            "SELECT COUNT(*) FROM search_history"
        ).fetchone()[0]
        first_row = conn.execute(
            "SELECT MIN(created_at) FROM user_interactions"
        ).fetchone()[0]
    days = 0
    if first_row:
        try:
            first = datetime.fromisoformat(first_row.replace("Z", "+00:00"))
            days = max(1, (datetime.now(timezone.utc) - first).days)
        except Exception:
            days = 0
    return {"interactions": interactions, "searches": searches, "days": days}
