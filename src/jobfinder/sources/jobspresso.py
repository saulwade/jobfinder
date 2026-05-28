"""Jobspresso — RSS WordPress (sin key)."""
from __future__ import annotations

import feedparser

from .base import Job, to_iso, clean


def fetch(query: str = "") -> list[Job]:
    parsed = feedparser.parse(
        "https://jobspresso.co/?feed=job_feed", agent="Mozilla/5.0 job-finder"
    )
    jobs: list[Job] = []
    for e in parsed.entries:
        # Jobspresso pone la empresa en dc:creator o en el título
        company = e.get("author", "") or e.get("dc_creator", "")
        jobs.append(
            Job(
                source="jobspresso",
                external_id=e.get("id", e.get("link", "")),
                url=e.get("link", ""),
                title=e.get("title", ""),
                company=clean(company),
                location="Remote",
                description=clean(e.get("summary", "")),
                tags=",".join(t.get("term", "") for t in e.get("tags", [])),
                posted_at=to_iso(e.get("published", "")),
            ).finalize()
        )
    return jobs
