"""Resumen diario por correo: envía las vacantes nuevas (matches) del día.

Usa SMTP de Gmail con credenciales en .env:
  GMAIL_USER=tucorreo@gmail.com
  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (App Password de Google, no tu clave normal)
Si faltan, se omite sin error.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

from .db import connect
from .profile import load_config

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _new_matches(hours: int = 25) -> list[dict]:
    cfg = load_config()
    thr = cfg["search"].get("min_score_to_apply", 65)
    conn = connect(ROOT / cfg["database"]["path"])
    rows = conn.execute(
        "SELECT * FROM jobs WHERE match_score >= ? AND status NOT IN "
        "('skipped','rejected') AND match_at >= datetime('now', ?) "
        "ORDER BY match_score DESC",
        (thr, f"-{hours} hours"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _html(jobs: list[dict]) -> str:
    rows = []
    for j in jobs:
        try:
            reasons = json.loads(j["match_reasons"]).get("reasons", "")
        except (json.JSONDecodeError, TypeError):
            reasons = ""
        sal = ""
        if j.get("salary_min_usd"):
            hi = f"–{j['salary_max_usd']:,}" if j.get("salary_max_usd") else ""
            sal = f" · ${j['salary_min_usd']:,}{hi} USD"
        comp = j["company"] or "(empresa no listada)"
        rows.append(
            f"<tr><td style='padding:10px 0;border-bottom:1px solid #eee'>"
            f"<b style='font-size:15px'>{j['title']}</b> "
            f"<span style='background:#eff4ff;color:#1849a9;border-radius:6px;"
            f"padding:1px 7px;font-size:12px'>Match {j['match_score']}</span><br>"
            f"<span style='color:#666;font-size:13px'>{comp} · {j['location']}{sal}</span><br>"
            f"<span style='color:#444;font-size:13px'>{reasons[:160]}</span><br>"
            f"<a href='{j['url']}' style='font-size:13px'>Ver vacante →</a></td></tr>"
        )
    return (
        f"<div style='font-family:Inter,Arial,sans-serif;max-width:640px;margin:auto'>"
        f"<h2>Job Finder · {len(jobs)} vacantes nuevas hoy</h2>"
        f"<p style='color:#666'>Trabajos remotos finanzas + tech que encajan con tus skills.</p>"
        f"<table style='width:100%;border-collapse:collapse'>{''.join(rows)}</table>"
        f"<p style='color:#999;font-size:12px;margin-top:20px'>Abre el panel para generar "
        f"CV y carta de las que te interesen.</p></div>"
    )


def send_if_configured(verbose: bool = True) -> bool:
    user = os.getenv("GMAIL_USER")
    pwd = os.getenv("GMAIL_APP_PASSWORD")
    if not user or not pwd:
        if verbose:
            print("[digest] sin GMAIL_USER/GMAIL_APP_PASSWORD en .env, se omite el correo")
        return False

    jobs = _new_matches()
    if not jobs:
        if verbose:
            print("[digest] no hay vacantes nuevas hoy, no se envía correo")
        return False

    msg = MIMEText(_html(jobs), "html", "utf-8")
    msg["Subject"] = f"Job Finder · {len(jobs)} vacantes nuevas hoy"
    msg["From"] = user
    msg["To"] = user

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls(context=ctx)
        s.login(user, pwd)
        s.send_message(msg)
    if verbose:
        print(f"[digest] correo enviado a {user} con {len(jobs)} vacantes")
    return True


if __name__ == "__main__":
    send_if_configured()
