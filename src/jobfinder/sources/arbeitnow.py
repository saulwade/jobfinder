"""Arbeitnow — https://www.arbeitnow.com/api/job-board-api (JSON, sin key)."""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean


def fetch(query: str = "") -> list[Job]:
    jobs: list[Job] = []
    for page in range(1, 4):  # ~300 vacantes
        r = http_get(
            "https://www.arbeitnow.com/api/job-board-api", params={"page": page}
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            break
        for item in data:
            jobs.append(
                Job(
                    source="arbeitnow",
                    external_id=str(item.get("slug", "")),
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("location", ""),
                    remote=1 if item.get("remote") else 0,
                    description=clean(item.get("description", "")),
                    tags=",".join(item.get("tags", []) + item.get("job_types", [])),
                    posted_at=to_iso(item.get("created_at")),
                ).finalize()
            )
    return jobs
