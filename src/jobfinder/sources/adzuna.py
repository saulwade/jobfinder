"""Adzuna — agregador grande con edición por país (incluye México).

API oficial gratuita. Requiere registro en https://developer.adzuna.com
y poner ADZUNA_APP_ID y ADZUNA_APP_KEY en el archivo .env.
"""
from __future__ import annotations

import os

from .base import Job, http_get, to_iso, clean

# Ediciones a consultar: México + globales con vacantes remotas internacionales.
COUNTRIES = ["mx", "us", "gb"]
QUERIES = ["finance analyst remote", "financial analyst", "fp&a", "data analyst finance"]


def fetch(query: str = "") -> list[Job]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return []  # sin keys, no hace nada (se activa al poner las keys en .env)

    jobs: list[Job] = []
    for country in COUNTRIES:
        for what in QUERIES:
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            params = {
                "app_id": app_id, "app_key": app_key,
                "results_per_page": 50, "what": what,
                "content-type": "application/json",
            }
            r = http_get(url, params=params)
            if r.status_code != 200:
                continue
            for j in r.json().get("results", []):
                loc = (j.get("location") or {}).get("display_name", "")
                jobs.append(Job(
                    source="adzuna", external_id=str(j.get("id", "")),
                    url=j.get("redirect_url", ""), title=j.get("title", ""),
                    company=(j.get("company") or {}).get("display_name", ""),
                    location=loc or "Remote",
                    salary_min_usd=_int(j.get("salary_min")),
                    salary_max_usd=_int(j.get("salary_max")),
                    description=clean(j.get("description", "")),
                    tags=(j.get("category") or {}).get("label", ""),
                    posted_at=to_iso(j.get("created")),
                ).finalize())
    return jobs


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
