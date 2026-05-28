"""Himalayas — https://himalayas.app/jobs/api (JSON, sin key)."""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean


def fetch(query: str = "") -> list[Job]:
    jobs: list[Job] = []
    for offset in (0, 100, 200):
        r = http_get(
            "https://himalayas.app/jobs/api",
            params={"limit": 100, "offset": offset},
        )
        r.raise_for_status()
        data = r.json().get("jobs", [])
        if not data:
            break
        for item in data:
            locs = item.get("locationRestrictions") or item.get("candidateLocations") or []
            jobs.append(
                Job(
                    source="himalayas",
                    external_id=str(item.get("guid") or item.get("id", "")),
                    url=item.get("applicationLink") or item.get("url", ""),
                    title=item.get("title", ""),
                    company=item.get("companyName", ""),
                    location=", ".join(locs) if isinstance(locs, list) else str(locs),
                    salary_min_usd=_int(item.get("minSalary")),
                    salary_max_usd=_int(item.get("maxSalary")),
                    description=clean(item.get("description", "")),
                    tags=",".join(item.get("categories", []) or []),
                    posted_at=to_iso(item.get("pubDate") or item.get("publishedDate")),
                ).finalize()
            )
    return jobs


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
