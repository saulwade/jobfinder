"""Fase 2: matching con IA. Claude rankea cada vacante contra el perfil.

Usa Haiku (barato) para el ranking masivo y prompt caching del perfil
(que es la parte estable y grande del prompt) para abaratar repeticiones.
"""
from __future__ import annotations

import json
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


def _render_profile(profile: dict) -> str:
    """Perfil + rúbrica como bloque estable y cacheable del system prompt."""
    t = profile["target"]
    return f"""Eres un reclutador técnico senior evaluando qué tan bien encaja un
candidato con vacantes. Debes ser estricto y realista.

# PERFIL DEL CANDIDATO
{yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)}

# CRITERIOS DE EVALUACIÓN (score 0-100)
Evalúa cada vacante contra el perfil considerando:
- Encaje de rol y skills (finanzas + tech, Python/SQL, FP&A, automatización, datos).
- Seniority: el candidato es junior/mid. Penaliza fuerte roles senior/director/VP/lead
  o que pidan 5+ años. Penaliza roles totalmente ajenos (ej. enfermería, ventas puras).
- Remoto real: debe ser remoto. Penaliza on-site/híbrido.
- Geografía: debe poder contratar desde México/LATAM o ser worldwide. Penaliza
  vacantes restringidas a "US only", "EU only", requisito de visa/clearance.
- Sueldo: bonus si cumple el piso de {t['min_salary_usd_year']} USD/año o más.
- Idioma: el candidato habla inglés C1 y español nativo. Penaliza vacantes que exijan
  alemán/francés nativo u otros idiomas que no domina.

# RANGOS DE SCORE
- 85-100: encaje excelente, debería aplicar ya.
- 70-84: buen encaje, vale la pena aplicar.
- 50-69: encaje parcial, dudoso.
- 0-49: mal encaje, descartar.

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


def run(limit: int | None = None, verbose: bool = True) -> dict:
    cfg = load_config()
    profile = load_profile()
    model = cfg["ai"].get("match_model", "claude-haiku-4-5")
    threshold = cfg["search"]["min_score_to_apply"]

    db_path = ROOT / cfg["database"]["path"]
    init_db(db_path)
    conn = connect(db_path)

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
            reasons = json.dumps(
                {"reasons": res.get("reasons", ""), "flags": res.get("flags", [])},
                ensure_ascii=False,
            )
            status = "matched" if score >= threshold else "skipped"
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
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            lim = int(a.split("=")[1])
    run(limit=lim)
