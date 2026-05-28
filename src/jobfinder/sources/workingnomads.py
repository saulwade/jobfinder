"""Working Nomads — https://www.workingnomads.com/api/exposed_jobs/ (JSON, sin key)."""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean


def fetch(query: str = "") -> list[Job]:
    r = http_get("https://www.workingnomads.com/api/exposed_jobs/")
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = data.get("jobs") or data.get("results") or []
    jobs: list[Job] = []
    for item in data:
        jobs.append(
            Job(
                source="workingnomads",
                external_id=str(item.get("id") or item.get("url", "")),
                url=item.get("url", ""),
                title=item.get("title", ""),
                company=item.get("company_name", ""),
                location=item.get("location") or "Remote",
                description=clean(item.get("description", "")),
                tags=clean(f"{item.get('category_name','')},{item.get('tags','')}"),
                posted_at=to_iso(item.get("pub_date")),
            ).finalize()
        )
    return jobs
