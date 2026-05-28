"""The Muse — https://www.themuse.com/api/public/jobs (JSON, sin key)."""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean


def fetch(query: str = "") -> list[Job]:
    categories = ["Accounting and Finance", "Data and Analytics", "Data Science"]
    jobs: list[Job] = []
    for page in range(0, 3):
        params = [("category", c) for c in categories] + [("page", page)]
        r = http_get("https://www.themuse.com/api/public/jobs", params=params)
        if r.status_code != 200:
            break
        for item in r.json().get("results", []):
            locs = [l.get("name", "") for l in item.get("locations", [])]
            is_remote = any("remote" in l.lower() or "flexible" in l.lower() for l in locs)
            company = (item.get("company") or {}).get("name", "")
            refs = item.get("refs") or {}
            jobs.append(
                Job(
                    source="themuse",
                    external_id=str(item.get("id", "")),
                    url=refs.get("landing_page", ""),
                    title=item.get("name", ""),
                    company=company,
                    location=", ".join(locs),
                    remote=1 if is_remote else 0,
                    description=clean(item.get("contents", "")),
                    tags=",".join(c.get("name", "") for c in item.get("categories", [])),
                    posted_at=to_iso(item.get("publication_date")),
                ).finalize()
            )
    return jobs
