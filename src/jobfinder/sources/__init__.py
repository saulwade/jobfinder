"""Registro de fuentes. Cada fetcher devuelve list[Job]."""
from __future__ import annotations

from . import (
    remoteok,
    remotive,
    weworkremotely,
    arbeitnow,
    himalayas,
    jobicy,
    themuse,
    jobspresso,
)

# nombre en config.yaml -> función fetch(query: str) -> list[Job]
REGISTRY = {
    "remoteok": remoteok.fetch,
    "remotive": remotive.fetch,
    "weworkremotely": weworkremotely.fetch,
    "arbeitnow": arbeitnow.fetch,
    "himalayas": himalayas.fetch,
    "jobicy": jobicy.fetch,
    "themuse": themuse.fetch,
    "jobspresso": jobspresso.fetch,
}
