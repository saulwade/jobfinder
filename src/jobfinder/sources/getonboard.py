"""Get on Board (getonbrd.com) — bolsa LATAM con muchas startups/pymes.

API pública sin key. Trae bandera de remoto y sueldo (mensual USD).
Ideal para vacantes que contratan desde México/LATAM.
"""
from __future__ import annotations

from .base import Job, http_get, to_iso, clean

QUERIES = [
    "finance", "financial analyst", "data analyst", "operations analyst",
    "business analyst", "automation", "accounting", "fp&a",
]


def fetch(query: str = "") -> list[Job]:
    jobs: list[Job] = []
    seen = set()
    for q in QUERIES:
        r = http_get(
            "https://www.getonbrd.com/api/v0/search/jobs",
            params={"query": q, "per_page": 50, "expand": '["company"]'},
        )
        if r.status_code != 200:
            continue
        payload = r.json()
        companies = {
            inc["id"]: inc.get("attributes", {}).get("name", "")
            for inc in payload.get("included", [])
            if inc.get("type") == "company"
        }
        for item in payload.get("data", []):
            jid = item.get("id")
            if jid in seen:
                continue
            seen.add(jid)
            a = item.get("attributes", {})
            comp_id = (
                item.get("relationships", {}).get("company", {})
                .get("data", {}) or {}
            ).get("id")
            # sueldo en GoB viene mensual USD -> anualizar para consistencia
            smin = _annual(a.get("min_salary"))
            smax = _annual(a.get("max_salary"))
            jobs.append(Job(
                source="getonboard", external_id=str(jid),
                url=(item.get("links", {}) or {}).get("public_url", ""),
                title=a.get("title", ""),
                company=companies.get(comp_id, ""),
                location="Remote" if a.get("remote") else (a.get("remote_modality") or ""),
                remote=1 if a.get("remote") else 0,
                salary_min_usd=smin, salary_max_usd=smax,
                description=clean(a.get("description", "")),
                tags=clean(a.get("functions_headline", "")),
                posted_at=to_iso(a.get("published_at")),
            ).finalize())
    return jobs


def _annual(monthly):
    try:
        m = float(monthly)
        return int(m * 12) if m else None
    except (TypeError, ValueError):
        return None
