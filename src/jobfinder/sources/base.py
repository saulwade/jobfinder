"""Modelo común de vacante + utilidades de normalización y dedupe."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

import requests

USER_AGENT = "job-finder/0.1 (personal use)"
TIMEOUT = 25


@dataclass
class Job:
    source: str
    url: str
    title: str
    company: str = ""
    location: str = ""
    remote: int = 1
    salary_text: str = ""
    salary_min_usd: int | None = None
    salary_max_usd: int | None = None
    description: str = ""
    tags: str = ""
    posted_at: str = ""
    external_id: str = ""
    fingerprint: str = ""

    def finalize(self) -> "Job":
        self.title = clean(self.title)
        self.company = clean(self.company)
        self.location = clean(self.location)
        self.fingerprint = make_fingerprint(self.title, self.company)
        if self.salary_text:
            lo, hi = parse_salary_usd(self.salary_text)
            self.salary_min_usd = self.salary_min_usd or lo
            self.salary_max_usd = self.salary_max_usd or hi
        return self

    def as_row(self) -> dict:
        return asdict(self)


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))      # strip HTML
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_fingerprint(title: str, company: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", f"{title}{company}".lower())
    return hashlib.sha1(key.encode()).hexdigest()


def parse_salary_usd(text: str) -> tuple[int | None, int | None]:
    """Extrae rango anual aproximado en USD desde texto libre. Best-effort."""
    if not text:
        return None, None
    t = text.lower()
    if "$" not in t and "usd" not in t and "k" not in t:
        return None, None
    nums = re.findall(r"(\d[\d,\.]*)\s*([kK])?", text)
    vals: list[int] = []
    for raw, k in nums:
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        if k:
            n *= 1000
        # asume montos anuales; ignora valores pequeños (horas, %)
        if n >= 1000:
            vals.append(int(n))
    if not vals:
        return None, None
    vals.sort()
    lo = vals[0]
    hi = vals[-1] if len(vals) > 1 else None
    return lo, hi


def to_iso(value) -> str:
    """Normaliza fechas variadas a ISO 8601."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except (OSError, ValueError):
            return ""
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s[:len(fmt) + 6], fmt).isoformat()
        except ValueError:
            continue
    return s


def http_get(url: str, **kwargs) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    headers.update(kwargs.pop("headers", {}))
    return requests.get(url, headers=headers, timeout=TIMEOUT, **kwargs)
