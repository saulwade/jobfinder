"""Conectores a ATS públicos (Greenhouse, Lever, Ashby) por lista de empresas.

APIs oficiales y gratuitas, sin key — leen las vacantes desde la fuente original
de cada empresa (las mismas que aparecen en LinkedIn, pero sin scrapear LinkedIn).
La lista de empresas vive en profile/companies.yaml.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .base import Job, http_get, to_iso, clean

ROOT = Path(__file__).resolve().parents[3]


def _companies() -> dict:
    f = ROOT / "profile" / "companies.yaml"
    if not f.exists():
        return {}
    return yaml.safe_load(f.read_text()) or {}


def _greenhouse(slug: str) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = http_get(url)
    if r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        out.append(Job(
            source="greenhouse", external_id=str(j.get("id", "")),
            url=j.get("absolute_url", ""), title=j.get("title", ""),
            company=slug.replace("-", " ").title(), location=loc or "Remote",
            description=clean(j.get("content", "")),
            posted_at=to_iso(j.get("updated_at")),
        ).finalize())
    return out


def _lever(slug: str) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = http_get(url)
    if r.status_code != 200:
        return []
    out = []
    for j in r.json():
        cat = j.get("categories", {}) or {}
        out.append(Job(
            source="lever", external_id=str(j.get("id", "")),
            url=j.get("hostedUrl", ""), title=j.get("text", ""),
            company=slug.replace("-", " ").title(),
            location=cat.get("location", "Remote"),
            description=clean(j.get("descriptionPlain") or j.get("description", "")),
            tags=clean(f"{cat.get('team','')},{cat.get('commitment','')}"),
            posted_at=to_iso(j.get("createdAt")),
        ).finalize())
    return out


def _ashby(slug: str) -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    r = http_get(url)
    if r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        out.append(Job(
            source="ashby", external_id=str(j.get("id", "")),
            url=j.get("jobUrl") or j.get("applyUrl", ""), title=j.get("title", ""),
            company=slug.replace("-", " ").title(),
            location=j.get("location", "Remote"),
            description=clean(j.get("descriptionPlain")
                              or j.get("descriptionHtml", "")),
            tags=clean(f"{j.get('department','')},{j.get('team','')}"),
            posted_at=to_iso(j.get("publishedAt")),
        ).finalize())
    return out


_PLATFORMS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def fetch(query: str = "") -> list[Job]:
    companies = _companies()
    jobs: list[Job] = []
    for platform, fn in _PLATFORMS.items():
        for slug in companies.get(platform, []) or []:
            try:
                got = fn(slug)
            except Exception:
                got = []
            jobs.extend(got)
    return jobs
