"""Orquestador de la Fase 1: fetch -> filtra -> dedupe -> guarda en SQLite."""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

from .db import connect, init_db
from .profile import load_config, load_profile
from .sources import REGISTRY

ROOT = Path(__file__).resolve().parents[2]

# Fuentes de alto volumen (boards de empresas): se pre-filtran por título para
# no ingerir ni evaluar miles de roles de ingeniería irrelevantes.
HIGH_VOLUME = {"greenhouse", "lever", "ashby", "smartrecruiters", "recruitee"}

# Fuentes que SOLO publican trabajos remotos: se confía en ellas como remotas.
INHERENTLY_REMOTE = {
    "remoteok", "remotive", "weworkremotely", "jobicy",
    "workingnomads", "jobspresso", "himalayas",
}
# Señales de remoto en texto libre.
_REMOTE_RE = re.compile(
    r"\bremote\b|\banywhere\b|distributed|work from home|\bwfh\b|"
    r"worldwide|fully remote|remote-first|remote first", re.I,
)
# Señales de presencial/híbrido que descalifican aunque digan "remote".
_ONSITE_RE = re.compile(r"\bon[\s-]?site\b|in[\s-]?office|hybrid", re.I)


def is_remote(job) -> bool:
    """Estricto: solo deja pasar trabajos realmente remotos."""
    loc_title = f"{job.title} {job.location} {job.tags}".lower()
    if _ONSITE_RE.search(loc_title):
        return False
    if job.source in INHERENTLY_REMOTE:
        return True
    # arbeitnow y themuse traen un flag de remoto confiable desde la fuente
    if job.source in ("arbeitnow", "themuse"):
        return job.remote == 1 or bool(_REMOTE_RE.search(loc_title))
    # boards de empresas (ATS): exige señal explícita de remoto en título/ubicación
    return bool(_REMOTE_RE.search(loc_title))
_RELEVANT_TITLE = re.compile(
    r"financ|fp&a|account|payroll|revenue|treasury|controller|\banalyst\b|"
    r"\bdata\b|business operations|bizops|revops|report|fintech|billing|audit|"
    r"\btax\b|bookkeep|strategy|operations analyst|finance", re.I,
)


def _passes_filters(job, profile) -> bool:
    target = profile["target"]
    blob = f"{job.title} {job.location} {job.description} {job.tags}".lower()

    # remoto estricto: si no es claramente remoto, descarta
    if target.get("remote_only") and not is_remote(job):
        return False

    # excluye ruido
    for kw in target.get("exclude_keywords", []):
        if kw.lower() in blob:
            return False

    # boards de empresas: solo títulos de finanzas/datos/operaciones
    if job.source in HIGH_VOLUME and not _RELEVANT_TITLE.search(job.title):
        return False

    return True


def _upsert(conn, job) -> bool:
    """Inserta si el fingerprint es nuevo. Devuelve True si insertó."""
    row = job.as_row()
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row)
    try:
        conn.execute(
            f"INSERT INTO jobs ({cols}) VALUES ({placeholders})", row
        )
        return True
    except Exception:  # UNIQUE(fingerprint) -> duplicado
        return False


def run(verbose: bool = True) -> dict:
    cfg = load_config()
    profile = load_profile()
    db_path = ROOT / cfg["database"]["path"]
    init_db(db_path)
    conn = connect(db_path)

    enabled = [
        name for name, s in cfg["sources"].items()
        if s.get("enabled") and name in REGISTRY
    ]
    query = profile["target"]["role_focus"].split("+")[0].strip().lower()  # "finance"

    stats = {"fetched": 0, "kept": 0, "inserted": 0, "by_source": {}, "errors": {}}

    for name in enabled:
        try:
            jobs = REGISTRY[name](query)
        except Exception as e:
            stats["errors"][name] = str(e)
            if verbose:
                print(f"  [{name}] ERROR: {e}")
                traceback.print_exc(limit=1)
            continue

        kept = ins = 0
        for job in jobs:
            stats["fetched"] += 1
            if not _passes_filters(job, profile):
                continue
            kept += 1
            stats["kept"] += 1
            if _upsert(conn, job):
                ins += 1
                stats["inserted"] += 1
        conn.commit()
        stats["by_source"][name] = {"fetched": len(jobs), "kept": kept, "new": ins}
        if verbose:
            print(f"  [{name}] fetched={len(jobs)} kept={kept} new={ins}")

    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    stats["db_total"] = total
    if verbose:
        print(
            f"\nResumen: {stats['fetched']} traídas, {stats['kept']} relevantes, "
            f"{stats['inserted']} nuevas. Total en DB: {total}"
        )
    return stats


if __name__ == "__main__":
    run(verbose="-q" not in sys.argv)
