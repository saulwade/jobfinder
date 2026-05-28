"""Fase 2: matching con IA. Claude rankea cada vacante contra el perfil.

Usa Haiku (barato) para el ranking masivo y prompt caching del perfil
(que es la parte estable y grande del prompt) para abaratar repeticiones.
"""
from __future__ import annotations

import json
import os.path
import re
import sys
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

from .db import connect, init_db
from .profile import load_config, load_profile

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

BATCH_SIZE = 12
DESC_CHARS = 700  # recorta descripciones para controlar tokens
SENIOR_CAP = 45   # tope de score para títulos por encima del nivel junior/mid

# Títulos que indican un nivel superior al del candidato (junior/mid sin gestión).
# Nota: "staff accountant" NO es senior, por eso "staff" solo cuenta junto a roles eng.
_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|principal|lead|head\s+of|director|vp|vice\s+president|"
    r"chief|founding|architect|manager|mgr)\b", re.I,
)


def is_above_level(title: str) -> bool:
    return bool(_SENIOR_RE.search(title or ""))


def _render_profile(profile: dict) -> str:
    """Perfil + rúbrica como bloque estable y cacheable del system prompt."""
    t = profile["target"]
    return f"""Eres un reclutador técnico senior evaluando qué tan bien encaja un
candidato con vacantes. Debes ser estricto y realista.

# PERFIL DEL CANDIDATO
{yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)}

# CÓMO EVALUAR: POR SKILLS, NO POR EL TÍTULO
Lo que importa es el SOLAPAMIENTO DE SKILLS entre lo que pide la vacante y lo que el
candidato sabe hacer. NO importa el nombre/departamento de la vacante. Un rol de
"Data Analyst", "Operations Analyst", "BI Analyst", "Automation Specialist",
"Analytics", "Financial Analyst", "RevOps", "Business Analyst", etc., todos cuentan
si usan las skills del candidato.

Skills del candidato (úsalas como referencia principal):
Python, SQL, Excel avanzado, Power BI, Tableau, Databricks, análisis y modelado de
datos, pipelines de datos, modelado financiero, FP&A, reporting/dashboards/KPIs,
automatización (n8n, Make, Power Automate, no-code), workflows de IA/LLM (OpenAI/Claude),
QuickBooks, reconciliaciones, operaciones financieras, unit economics, pricing.

# REGLA DE SENIORITY (aplícala primero)
El candidato es JUNIOR/MID (~2 años, incluye prácticas) y SIN gestión de equipos.
Si la vacante es claramente superior — "Senior", "Sr.", "Lead", "Principal", "Staff",
"Manager", "Head of", "Director", "VP", "Chief", "Founding", o pide 4+ años o liderar
un equipo — el score MÁXIMO es 45 (descártala). Ideales: Analyst, Associate, Junior,
Entry, Coordinator, Specialist.

# CRITERIOS (score 0-100), una vez pasada la regla de seniority
- SOLAPAMIENTO DE SKILLS (lo más importante): qué tanto de lo que pide la vacante
  el candidato ya lo sabe hacer. Más skills en común = score más alto.
- Remoto: debe ser remoto (las no-remotas ya se filtraron antes).
- Idioma: inglés C1 y español nativo; penaliza si exigen otro idioma (alemán, francés…).
- Geografía: si está restringida a un país que no es México/LATAM/worldwide, NO la
  descartes, solo bájale un poco y marca la bandera "geo_restricted".
- Tamaño de empresa: NO penalices (startup/pyme/grande, todas valen).
- Penaliza solo roles que NO usan sus skills (ej. enfermería, ventas puras, soporte,
  ingeniería de software pesada que requiere CS/system design que él no tiene).

# RANGOS DE SCORE
- 85-100: la vacante pide justo las skills que él tiene, nivel correcto. Aplicar ya.
- 70-84: buen solapamiento de skills, nivel correcto. Vale la pena aplicar.
- 50-69: solapamiento parcial de skills.
- 0-49: pocas skills en común o nivel demasiado alto.

# FORMATO DE SALIDA
Devuelve SOLO un array JSON válido, sin texto adicional, con un objeto por vacante:
[{{"id": <id>, "score": <0-100>, "reasons": "<1-2 frases en español>", "flags": ["remote_ok"|"seniority_high"|"geo_restricted"|"salary_ok"|"language_mismatch"...]}}]
"""


def _job_block(row) -> str:
    desc = (row["description"] or "")[:DESC_CHARS]
    sal = ""
    if row["salary_min_usd"] or row["salary_max_usd"]:
        sal = f" | salary_usd: {row['salary_min_usd']}-{row['salary_max_usd']}"
    return (
        f"--- id: {row['id']}\n"
        f"title: {row['title']}\n"
        f"company: {row['company']} | location: {row['location']} | "
        f"remote_flag: {row['remote']}{sal}\n"
        f"tags: {row['tags']}\n"
        f"description: {desc}"
    )


def _score_batch(client, model, system_text, rows) -> list[dict]:
    jobs_text = "\n\n".join(_job_block(r) for r in rows)
    user_msg = (
        f"Evalúa estas {len(rows)} vacantes. Devuelve el array JSON.\n\n{jobs_text}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=[{"type": "text", "text": system_text,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return _parse_json_array(text), resp.usage


def _parse_json_array(text: str) -> list[dict]:
    text = text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []


# estados que NO se deben sobrescribir al re-evaluar
PROTECTED = ("applied", "interview", "rejected")


def run(limit: int | None = None, rescore: bool = False, verbose: bool = True) -> dict:
    cfg = load_config()
    profile = load_profile()
    model = cfg["ai"].get("match_model", "claude-haiku-4-5")
    threshold = cfg["search"]["min_score_to_apply"]

    db_path = ROOT / cfg["database"]["path"]
    init_db(db_path)
    conn = connect(db_path)

    if rescore:
        # re-evalúa el pool remoto; no toca terminales ni las marcadas no-remotas
        q = ("SELECT * FROM jobs WHERE status NOT IN "
             "('applied','interview','rejected') "
             "AND COALESCE(notes,'') != 'no remoto' ORDER BY id")
    else:
        q = "SELECT * FROM jobs WHERE match_score IS NULL ORDER BY id"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()

    if not rows:
        print("No hay vacantes sin evaluar.")
        conn.close()
        return {"scored": 0}

    client = anthropic.Anthropic()
    system_text = _render_profile(profile)

    stats = {"scored": 0, "matched": 0, "cache_read": 0, "in": 0, "out": 0}
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        results, usage = _score_batch(client, model, system_text, batch)
        stats["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
        stats["in"] += usage.input_tokens
        stats["out"] += usage.output_tokens

        by_id = {r["id"]: r for r in batch}
        for res in results:
            jid = res.get("id")
            if jid not in by_id:
                continue
            score = int(res.get("score", 0))
            # tope determinista por seniority (no depende del modelo)
            if is_above_level(by_id[jid]["title"]) and score > SENIOR_CAP:
                score = SENIOR_CAP
            reasons = json.dumps(
                {"reasons": res.get("reasons", ""), "flags": res.get("flags", [])},
                ensure_ascii=False,
            )
            if score >= threshold:
                # preserva 'tailored' si ya tiene CV generado (no rehacer trabajo)
                cv = by_id[jid]["cv_path"]
                status = "tailored" if cv and os.path.exists(cv) else "matched"
            else:
                status = "skipped"
            conn.execute(
                "UPDATE jobs SET match_score=?, match_reasons=?, "
                "match_at=datetime('now'), status=?, updated_at=datetime('now') "
                "WHERE id=?",
                (score, reasons, status, jid),
            )
            stats["scored"] += 1
            if score >= threshold:
                stats["matched"] += 1
        conn.commit()
        if verbose:
            print(f"  lote {i//BATCH_SIZE + 1}: {len(results)} evaluadas "
                  f"(cache_read={stats['cache_read']})")

    conn.close()
    if verbose:
        print(f"\nEvaluadas: {stats['scored']} | match (>= {threshold}): "
              f"{stats['matched']} | tokens in={stats['in']} out={stats['out']} "
              f"cache_read={stats['cache_read']}")
    return stats


if __name__ == "__main__":
    lim = None
    rescore = "--rescore" in sys.argv
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            lim = int(a.split("=")[1])
    run(limit=lim, rescore=rescore)
