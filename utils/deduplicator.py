"""Job deduplication via SHA-256 hash."""

import hashlib


def make_job_hash(portal: str, title: str, company: str, apply_url: str) -> str:
    """Return a stable hex digest that uniquely identifies a job listing."""
    key = f"{portal}|{title.lower().strip()}|{company.lower().strip()}|{apply_url.strip()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
