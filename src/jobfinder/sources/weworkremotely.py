"""We Work Remotely — RSS (sin key)."""
from __future__ import annotations

import feedparser

from .base import Job, to_iso, clean

FEEDS = [
    "https://weworkremotely.com/remote-jobs.rss",  # feed completo; el matcher filtra relevancia
]


def fetch(query: str = "") -> list[Job]:
    jobs: list[Job] = []
    for feed_url in FEEDS:
        parsed = feedparser.parse(feed_url)
        for e in parsed.entries:
            # WWR titula como "Company: Position"
            raw = e.get("title", "")
            if ":" in raw:
                company, _, title = raw.partition(":")
            else:
                company, title = "", raw
            jobs.append(
                Job(
                    source="weworkremotely",
                    external_id=e.get("id", e.get("link", "")),
                    url=e.get("link", ""),
                    title=title.strip(),
                    company=company.strip(),
                    location="Remote",
                    description=clean(e.get("summary", "")),
                    tags=",".join(t.get("term", "") for t in e.get("tags", [])),
                    posted_at=to_iso(e.get("published", "")),
                ).finalize()
            )
    return jobs
