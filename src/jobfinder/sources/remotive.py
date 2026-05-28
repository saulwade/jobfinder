"""Remotive — https://remotive.com/api/remote-jobs (JSON, sin key)."""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean


def fetch(query: str = "finance") -> list[Job]:
    params = {"limit": 200}
    if query:
        params["search"] = query
    r = http_get("https://remotive.com/api/remote-jobs", params=params)
    r.raise_for_status()
    jobs: list[Job] = []
    for item in r.json().get("jobs", []):
        jobs.append(
            Job(
                source="remotive",
                external_id=str(item.get("id", "")),
                url=item.get("url", ""),
                title=item.get("title", ""),
                company=item.get("company_name", ""),
                location=item.get("candidate_required_location", "Remote"),
                salary_text=clean(item.get("salary", "")),
                description=clean(item.get("description", "")),
                tags=",".join(item.get("tags", [])),
                posted_at=to_iso(item.get("publication_date")),
            ).finalize()
        )
    return jobs
