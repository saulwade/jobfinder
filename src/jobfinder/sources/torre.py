"""Torre.ai — red de trabajo remoto global/LATAM con startups y pymes.

API pública sin key (POST a su buscador de oportunidades).
"""
from __future__ import annotations

import requests

from .base import Job, USER_AGENT, TIMEOUT, clean, to_iso

QUERIES = [
    "financial analyst", "data analyst", "operations analyst",
    "business analyst", "automation", "fp&a", "accounting",
]


def fetch(query: str = "") -> list[Job]:
    jobs: list[Job] = []
    seen = set()
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    for q in QUERIES:
        body = {"and": [
            {"remote": {"term": True}},
            {"skill/role": {"text": q, "experience": "potential-to-develop"}},
        ]}
        try:
            r = requests.post(
                "https://search.torre.co/opportunities/_search/",
                params={"size": 30, "lang": "en"}, json=body,
                headers=headers, timeout=TIMEOUT,
            )
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        for j in r.json().get("results", []):
            jid = j.get("id")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            orgs = j.get("organizations") or []
            company = orgs[0].get("name", "") if orgs else ""
            comp = (j.get("compensation") or {}).get("data", {}) or {}
            smin, smax = _annual(comp)
            jobs.append(Job(
                source="torre", external_id=str(jid),
                url=f"https://torre.ai/post/{jid}",
                title=j.get("objective", ""), company=company,
                location="Remote" if j.get("remote") else "",
                remote=1 if j.get("remote") else 0,
                salary_min_usd=smin, salary_max_usd=smax,
                description=clean(j.get("tagline", "")),
                tags=",".join(s.get("name", "") for s in (j.get("skills") or [])[:8]),
                posted_at=to_iso(j.get("created")),
            ).finalize())
    return jobs


def _annual(comp: dict):
    """Anualiza el rango de compensación de Torre (mensual/anual/hora)."""
    cur = comp.get("currency")
    if cur and cur != "USD":
        return None, None
    lo, hi = comp.get("minAmount") or 0, comp.get("maxAmount") or 0
    per = comp.get("periodicity", "")
    mult = {"monthly": 12, "yearly": 1, "hourly": 2080, "weekly": 52}.get(per, 0)
    if not mult:
        return None, None
    lo, hi = int(lo * mult), int(hi * mult)
    return (lo or None), (hi or None)
