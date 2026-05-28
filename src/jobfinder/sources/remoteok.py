"""RemoteOK — https://remoteok.com/api (JSON, sin key)."""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean


def fetch(query: str = "") -> list[Job]:
    r = http_get("https://remoteok.com/api")
    r.raise_for_status()
    data = r.json()
    jobs: list[Job] = []
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue  # el primer elemento es aviso legal
        tags = item.get("tags") or []
        jobs.append(
            Job(
                source="remoteok",
                external_id=str(item.get("id", "")),
                url=item.get("url") or item.get("apply_url", ""),
                title=item.get("position") or item.get("title", ""),
                company=item.get("company", ""),
                location=item.get("location", "Remote"),
                salary_text=clean(
                    f"{item.get('salary_min','')} {item.get('salary_max','')}".strip()
                ),
                salary_min_usd=_int(item.get("salary_min")),
                salary_max_usd=_int(item.get("salary_max")),
                description=clean(item.get("description", "")),
                tags=",".join(tags),
                posted_at=to_iso(item.get("date") or item.get("epoch")),
            ).finalize()
        )
    return jobs


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
