"""Panel local (Streamlit) para revisar matches y aplicar — human-in-the-loop.

Correr:  .venv/bin/streamlit run src/jobfinder/app.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
DB = ROOT / CFG["database"]["path"]
WEEKLY_TARGET = CFG["search"].get("weekly_application_target", 30)

STATUS_LABELS = {
    "tailored": "Listo para aplicar",
    "applied": "Aplicado",
    "interview": "Entrevista",
    "rejected": "Rechazado",
    "skipped": "Descartado",
    "matched": "Sin adaptar",
    "new": "Nuevo",
}
# estados que el usuario asigna desde el detalle
PIPELINE = ["tailored", "applied", "interview", "rejected", "skipped"]

# ----------------------------- data ---------------------------------------

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


@st.cache_data(ttl=4)
def load_jobs(statuses: tuple[str, ...], min_score: int, query: str):
    c = conn()
    rows = c.execute(
        "SELECT * FROM jobs WHERE match_score >= ? ORDER BY match_score DESC", (min_score,)
    ).fetchall()
    c.close()
    q = query.lower().strip()
    out = []
    for r in rows:
        d = dict(r)
        if statuses and d["status"] not in statuses:
            continue
        if q and q not in f"{d['title']} {d['company']} {d['tags']}".lower():
            continue
        out.append(d)
    return out


@st.cache_data(ttl=4)
def counts():
    c = conn()
    data = {s: c.execute("SELECT COUNT(*) FROM jobs WHERE status=?", (s,)).fetchone()[0]
            for s in STATUS_LABELS}
    c.close()
    return data


def get_job(job_id: int):
    c = conn()
    r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    c.close()
    return dict(r) if r else None


def update_status(job_id: int, status: str):
    c = conn()
    c.execute("UPDATE jobs SET status=?, updated_at=datetime('now') WHERE id=?",
              (status, job_id))
    c.commit()
    c.close()
    counts.clear()
    load_jobs.clear()


def reasons_of(d: dict) -> tuple[str, list[str]]:
    if not d.get("match_reasons"):
        return "", []
    try:
        r = json.loads(d["match_reasons"])
        return r.get("reasons", ""), r.get("flags", [])
    except json.JSONDecodeError:
        return d["match_reasons"], []


def read_doc(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    for cand in (p.with_suffix(".md"), p):
        if cand.exists():
            return cand.read_text()
    return ""


def salary_str(d: dict) -> str:
    if not d.get("salary_min_usd"):
        return ""
    hi = f"–{d['salary_max_usd']:,}" if d.get("salary_max_usd") else ""
    return f"${d['salary_min_usd']:,}{hi} USD"

# ----------------------------- styling ------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', sans-serif !important; }
.stApp { background: #f7f7f8; }
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 880px; }

/* tarjetas nativas con borde */
[data-testid="stVerticalBlockBorderWrapper"] { background:#fff; border-radius:14px; }
div[data-testid="stMetric"] { background:#fff; border:1px solid #ececec; border-radius:14px;
  padding:14px 16px; }
div[data-testid="stMetricValue"] { font-size:1.5rem; font-weight:700; color:#18181b; }
div[data-testid="stMetricLabel"] p { color:#71717a; font-size:.76rem; font-weight:500;
  text-transform:uppercase; letter-spacing:.04em; }

.title-row { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
.j-title { font-weight:600; font-size:1.04rem; color:#18181b; margin:0; line-height:1.3; }
.j-meta { color:#71717a; font-size:.84rem; margin:3px 0 0; }
.j-reason { color:#52525b; font-size:.85rem; margin:9px 0 2px; line-height:1.45; }

.badge { display:inline-block; font-size:.74rem; font-weight:600; padding:3px 9px;
  border-radius:7px; white-space:nowrap; }
.b-green { background:#ecfdf3; color:#067647; border:1px solid #abefc6; }
.b-blue  { background:#eff4ff; color:#1849a9; border:1px solid #b2ccff; }
.b-gray  { background:#f4f4f5; color:#52525b; border:1px solid #e4e4e7; }

.pill { display:inline-block; font-size:.72rem; font-weight:600; padding:2px 9px;
  border-radius:999px; border:1px solid; margin-top:8px; }
.p-tailored { background:#f4f4f5; color:#3f3f46; border-color:#e4e4e7; }
.p-applied  { background:#eff4ff; color:#1849a9; border-color:#b2ccff; }
.p-interview{ background:#fef6e7; color:#92600a; border-color:#fce4a6; }
.p-rejected { background:#fef3f2; color:#b42318; border-color:#fecdca; }
.p-skipped, .p-matched, .p-new { background:#f4f4f5; color:#a1a1aa; border-color:#e4e4e7; }

.flag { display:inline-block; font-size:.7rem; color:#52525b; background:#f4f4f5;
  border:1px solid #e4e4e7; border-radius:6px; padding:1px 7px; margin:0 4px 4px 0; }

.stButton button, .stLinkButton a { border-radius:9px; font-weight:500; }

/* preview de documentos en el modal: encabezados a tamaño legible */
[data-testid="stDialog"] h1 { font-size:1.25rem !important; margin:.2rem 0; }
[data-testid="stDialog"] h2 { font-size:1.02rem !important; margin:.6rem 0 .2rem;
  border-bottom:1px solid #ececec; padding-bottom:2px; }
[data-testid="stDialog"] h3 { font-size:.92rem !important; }
[data-testid="stDialog"] p, [data-testid="stDialog"] li { font-size:.86rem; }
</style>
"""


def score_badge(score: int) -> str:
    cls = "b-green" if score >= 85 else "b-blue" if score >= 70 else "b-gray"
    return f"<span class='badge {cls}'>Match {score}</span>"


def status_pill(status: str) -> str:
    return f"<span class='pill p-{status}'>{STATUS_LABELS.get(status, status)}</span>"

# ----------------------------- detail modal --------------------------------

@st.dialog(" ", width="large")
def show_detail(job_id: int):
    job = get_job(job_id)
    if not job:
        st.write("No encontrado.")
        return
    reasons, flags = reasons_of(job)
    sal = salary_str(job)

    st.markdown(f"### {job['title']}")
    meta = f"{job['company']} · {job['location']} · vía {job['source']}"
    if sal:
        meta += f" · {sal}"
    st.markdown(f"<p class='j-meta'>{meta} {score_badge(job['match_score'])}</p>",
                unsafe_allow_html=True)
    if flags:
        st.markdown("".join(f"<span class='flag'>{f}</span>" for f in flags),
                    unsafe_allow_html=True)
    if reasons:
        st.markdown(f"<p class='j-reason'>{reasons}</p>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    c1.link_button("Abrir vacante ↗", job["url"], use_container_width=True)
    pdf = job.get("cv_path", "") or ""
    if pdf.endswith(".pdf") and Path(pdf).exists():
        c2.download_button("Descargar CV (PDF)", Path(pdf).read_bytes(),
                           file_name=Path(pdf).name, mime="application/pdf",
                           use_container_width=True)
    else:
        c2.button("CV no generado", disabled=True, use_container_width=True)

    cur = job["status"] if job["status"] in PIPELINE else "tailored"
    new = st.radio("Estado de la postulación", PIPELINE, index=PIPELINE.index(cur),
                   format_func=lambda s: STATUS_LABELS[s], horizontal=True)
    if new != job["status"]:
        update_status(job["id"], new)
        st.toast(f"Estado: {STATUS_LABELS[new]}")
        st.rerun()

    st.divider()
    t1, t2, t3 = st.tabs(["CV adaptado", "Carta", "Respuestas"])
    t1.markdown(read_doc(job.get("cv_path")) or "_No generado._")
    t2.markdown(read_doc(job.get("cover_path")) or "_No generada._")
    t3.markdown(read_doc(job.get("answers_path")) or "_No generadas._")

# ----------------------------- page ----------------------------------------

st.set_page_config(page_title="Job Finder", page_icon="\U0001F4BC", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)

cnt = counts()

st.markdown("## Job Finder")
st.caption("Trabajos remotos finanzas + tech, adaptados a tu perfil y nivel")

mc = st.columns(4)
mc[0].metric("Por aplicar", cnt.get("tailored", 0))
mc[1].metric("Aplicados", cnt.get("applied", 0))
mc[2].metric("Entrevistas", cnt.get("interview", 0))
mc[3].metric("Meta semanal", f"{cnt.get('applied', 0)}/{WEEKLY_TARGET}")

with st.sidebar:
    st.markdown("### Filtros")
    sel_status = st.multiselect(
        "Estado", list(STATUS_LABELS.keys()),
        default=["tailored", "applied", "interview"],
        format_func=lambda s: STATUS_LABELS[s])
    min_score = st.slider("Score mínimo", 0, 100, 70, 5)
    query = st.text_input("Buscar", placeholder="título, empresa, skill…")
    st.divider()
    st.caption("Fuentes activas")
    st.caption(", ".join(k for k, v in CFG["sources"].items() if v.get("enabled")))

jobs = load_jobs(tuple(sel_status), min_score, query)

st.write("")
st.markdown(f"**{len(jobs)} vacantes**")

if not jobs:
    st.info("No hay vacantes con estos filtros. Baja el score mínimo o cambia el estado.")

for d in jobs:
    reasons, _ = reasons_of(d)
    sal = salary_str(d)
    with st.container(border=True):
        st.markdown(
            f"<div class='title-row'><p class='j-title'>{d['title']}</p>"
            f"{score_badge(d['match_score'])}</div>"
            f"<p class='j-meta'>{d['company']} · {d['location']}"
            f"{' · ' + sal if sal else ''}</p>"
            f"<p class='j-reason'>{reasons[:150]}</p>"
            f"{status_pill(d['status'])}",
            unsafe_allow_html=True)
        b1, b2 = st.columns([1, 1])
        if b1.button("Ver materiales", key=f"d{d['id']}", use_container_width=True,
                     type="primary"):
            show_detail(d["id"])
        b2.link_button("Abrir vacante ↗", d["url"], use_container_width=True)
