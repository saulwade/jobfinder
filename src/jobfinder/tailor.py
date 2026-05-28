"""Fase 3: adapta CV (una hoja, ATS), carta y respuestas para cada vacante.

Usa Claude Opus (calidad alta) con prompt caching del CV base + perfil.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from .db import connect, init_db
from .profile import load_config, load_master_cv, load_profile
from .render import render_cv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OUT_CV = ROOT / "output" / "cv"
OUT_COVER = ROOT / "output" / "cover_letters"
OUT_ANSWERS = ROOT / "output" / "answers"

SYSTEM_TMPL = """Eres un experto en redacción de CVs ATS-friendly y cartas de
presentación para roles de finanzas + tecnología. Adaptas el material del
candidato a cada vacante siguiendo las mejores prácticas.

# CV BASE DEL CANDIDATO (markdown)
{master_cv}

# PERFIL ESTRUCTURADO
{profile}

# REGLAS ESTRICTAS PARA EL CV ADAPTADO
1. DEBE caber en UNA sola página (sé conciso; recorta bullets menos relevantes).
2. ATS-friendly: sin tablas, sin columnas, sin gráficos. Solo encabezados, texto y bullets.
3. Reordena y reescribe los bullets para resaltar lo más relevante a ESTA vacante;
   integra de forma natural las keywords del puesto (sin inventar experiencia).
4. NUNCA inventes datos, empleos, fechas ni métricas. Solo reordena/reformula lo real.
5. Mantén nombre y datos de contacto en el encabezado.
6. Verbos de acción fuertes, bullets cuantificados, en inglés (los CVs van a vacantes en inglés
   salvo que la vacante esté claramente en español, en cuyo caso usa español).

# CARTA DE PRESENTACIÓN
3-4 párrafos, específica a la empresa y rol, conectando la experiencia real del candidato
con lo que pide la vacante. Tono profesional y genuino, no genérico.

# RESPUESTAS A PREGUNTAS COMUNES DE APLICACIÓN
Genera borradores para: "Why do you want to work here?", "Why are you a good fit?",
"Salary expectations" (usa el rango del perfil), y "When can you start?".

# FORMATO DE SALIDA
Devuelve EXACTAMENTE tres secciones separadas por estos delimitadores literales,
sin texto adicional antes, entre o después:
===CV===
(aquí el CV en markdown: '# Nombre', línea de contacto, luego '## SECCIONES' y bullets con '-')
===COVER===
(aquí la carta de presentación)
===ANSWERS===
(aquí las respuestas a las preguntas comunes)
"""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _build_user_msg(job) -> str:
    return (
        "Adapta el material para esta vacante:\n\n"
        f"Título: {job['title']}\n"
        f"Empresa: {job['company']}\n"
        f"Ubicación: {job['location']}\n"
        f"URL: {job['url']}\n\n"
        f"Descripción:\n{job['description'][:2200]}"
    )


def _parse_sections(text: str) -> dict | None:
    """Parsea la salida delimitada por ===CV===/===COVER===/===ANSWERS===."""
    if "===CV===" not in text:
        return None
    after_cv = text.split("===CV===", 1)[1]
    cv, _, rest = after_cv.partition("===COVER===")
    cover, _, answers = rest.partition("===ANSWERS===")
    cv = cv.strip()
    if not cv:
        return None
    return {
        "cv_markdown": cv,
        "cover_letter": cover.strip(),
        "answers": answers.strip(),
    }


def tailor_one(client, model, system_text, job) -> dict:
    resp = client.messages.create(
        model=model,
        max_tokens=4500,
        system=[{"type": "text", "text": system_text,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": _build_user_msg(job)}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    data = _parse_sections(text)
    return data, resp.usage


def run(limit: int | None = None, job_id: int | None = None, verbose: bool = True) -> dict:
    cfg = load_config()
    profile = load_profile()
    master_cv = load_master_cv()
    model = cfg["ai"]["model"]

    db_path = ROOT / cfg["database"]["path"]
    init_db(db_path)
    conn = connect(db_path)

    if job_id:
        q, args = "SELECT * FROM jobs WHERE id=?", (job_id,)
    else:
        q = "SELECT * FROM jobs WHERE status='matched' ORDER BY match_score DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        args = ()
    jobs = conn.execute(q, args).fetchall()
    if not jobs:
        print("No hay vacantes en estado 'matched' para adaptar.")
        conn.close()
        return {"tailored": 0}

    import yaml
    system_text = SYSTEM_TMPL.format(
        master_cv=master_cv,
        profile=yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
    )
    client = anthropic.Anthropic()

    stats = {"tailored": 0, "in": 0, "out": 0, "cache_read": 0, "pdf": 0}
    for job in jobs:
        data, usage = tailor_one(client, model, system_text, job)
        stats["in"] += usage.input_tokens
        stats["out"] += usage.output_tokens
        stats["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
        if not data:
            # El modelo no entregó CV (normalmente porque marcó mal-encaje):
            # actúa como segundo filtro y descarta la vacante.
            conn.execute(
                "UPDATE jobs SET status='skipped', notes=?, "
                "updated_at=datetime('now') WHERE id=?",
                ("tailor: descartada (encaje insuficiente o sin CV)", job["id"]),
            )
            conn.commit()
            stats["skipped"] = stats.get("skipped", 0) + 1
            if verbose:
                print(f"  [id {job['id']}] descartada por el tailor (mal encaje)")
            continue

        base = f"{job['id']}_{_slug(job['company'] or 'na')}_{_slug(job['title'])}"
        cv_paths = render_cv(data.get("cv_markdown", ""), OUT_CV / base)
        if "pdf" in cv_paths:
            stats["pdf"] += 1

        OUT_COVER.mkdir(parents=True, exist_ok=True)
        OUT_ANSWERS.mkdir(parents=True, exist_ok=True)
        cover_path = OUT_COVER / f"{base}.md"
        cover_path.write_text(data.get("cover_letter", ""))
        ans_path = OUT_ANSWERS / f"{base}.md"
        ans_path.write_text(data.get("answers", ""))

        conn.execute(
            "UPDATE jobs SET cv_path=?, cover_path=?, answers_path=?, "
            "status='tailored', updated_at=datetime('now') WHERE id=?",
            (cv_paths.get("pdf") or cv_paths.get("html"),
             str(cover_path), str(ans_path), job["id"]),
        )
        conn.commit()
        stats["tailored"] += 1
        if verbose:
            tag = "PDF" if "pdf" in cv_paths else "HTML"
            print(f"  [{job['match_score']}] {job['title'][:40]:40} -> {base} ({tag})")

    conn.close()
    if verbose:
        print(f"\nAdaptadas: {stats['tailored']} | PDFs: {stats['pdf']} | "
              f"tokens in={stats['in']} out={stats['out']} cache_read={stats['cache_read']}")
    return stats


if __name__ == "__main__":
    lim, jid = None, None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            lim = int(a.split("=")[1])
        elif a.startswith("--id="):
            jid = int(a.split("=")[1])
    run(limit=lim, job_id=jid)
