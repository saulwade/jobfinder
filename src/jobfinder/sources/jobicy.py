"""Jobicy — https://jobicy.com/api/v2/remote-jobs (JSON, sin key)."""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean


def fetch(query: str = "finance") -> list[Job]:
    params = {"count": 50}
    if query:
        params["tag"] = query
    r = http_get("https://jobicy.com/api/v2/remote-jobs", params=params)
    r.raise_for_status()
    jobs: list[Job] = []
    for item in r.json().get("jobs", []):
        geo = item.get("jobGeo", "Remote")
        jobs.append(
            Job(
                source="jobicy",
                external_id=str(item.get("id", "")),
                url=item.get("url", ""),
                title=item.get("jobTitle", ""),
                company=item.get("companyName", ""),
                location=geo,
                salary_min_usd=_int(item.get("annualSalaryMin")),
                salary_max_usd=_int(item.get("annualSalaryMax")),
                salary_text=clean(item.get("salaryCurrency", "")),
                description=clean(item.get("jobDescription") or item.get("jobExcerpt", "")),
                tags=",".join(item.get("jobIndustry", []) or [])
                + ","
                + ",".join(item.get("jobType", []) or []),
                posted_at=to_iso(item.get("pubDate")),
            ).finalize()
        )
    return jobs


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
