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
STATUS_ORDER = ["tailored", "applied", "interview", "rejected", "skipped"]

# ----------------------------- data ---------------------------------------

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


@st.cache_data(ttl=5)
def load_jobs(statuses: tuple[str, ...], min_score: int, query: str):
    c = conn()
    rows = c.execute(
        "SELECT * FROM jobs WHERE match_score >= ? ORDER BY match_score DESC", (min_score,)
    ).fetchall()
    c.close()
    out = []
    q = query.lower().strip()
    for r in rows:
        d = dict(r)
        if statuses and d["status"] not in statuses:
            continue
        if q and q not in f"{d['title']} {d['company']} {d['tags']}".lower():
            continue
        out.append(d)
    return out


def counts():
    c = conn()
    data = {s: c.execute("SELECT COUNT(*) FROM jobs WHERE status=?", (s,)).fetchone()[0]
            for s in STATUS_LABELS}
    c.close()
    return data


def update_status(job_id: int, status: str):
    c = conn()
    c.execute("UPDATE jobs SET status=?, updated_at=datetime('now') WHERE id=?",
              (status, job_id))
    c.commit()
    c.close()
    st.cache_data.clear()


def reasons_of(d: dict) -> tuple[str, list[str]]:
    if not d.get("match_reasons"):
        return "", []
    try:
        r = json.loads(d["match_reasons"])
        return r.get("reasons", ""), r.get("flags", [])
    except json.JSONDecodeError:
        return d["match_reasons"], []


def read_file(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    # guarda en DB el pdf/html; el .md vive junto
    md = p.with_suffix(".md")
    for cand in (md, p):
        if cand.exists():
            return cand.read_text()
    return ""

# ----------------------------- styling ------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #fafafa; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2.2rem; max-width: 1180px; }

.hero-title { font-size: 1.7rem; font-weight: 700; color: #18181b; letter-spacing: -.02em; margin: 0; }
.hero-sub { color: #71717a; font-size: .9rem; margin: 2px 0 0; }

.metric-card { background:#fff; border:1px solid #ececec; border-radius:14px; padding:16px 18px; }
.metric-num { font-size:1.6rem; font-weight:700; color:#18181b; line-height:1; }
.metric-lab { color:#71717a; font-size:.78rem; font-weight:500; margin-top:6px; text-transform:uppercase; letter-spacing:.04em; }

.job-card { background:#fff; border:1px solid #ececec; border-radius:14px; padding:16px 18px; margin-bottom:12px;
  transition: border-color .15s, box-shadow .15s; }
.job-card:hover { border-color:#d4d4d8; box-shadow:0 2px 12px rgba(0,0,0,.05); }
.job-card.sel { border-color:#18181b; box-shadow:0 2px 16px rgba(0,0,0,.07); }
.job-title { font-weight:600; font-size:1.02rem; color:#18181b; margin:0; line-height:1.3; }
.job-meta { color:#71717a; font-size:.82rem; margin:3px 0 0; }
.job-reason { color:#52525b; font-size:.82rem; margin:8px 0 0; line-height:1.45; }

.badge { display:inline-block; font-size:.74rem; font-weight:600; padding:3px 9px; border-radius:7px; }
.b-green { background:#ecfdf3; color:#067647; border:1px solid #abefc6; }
.b-blue  { background:#eff4ff; color:#1849a9; border:1px solid #b2ccff; }
.b-gray  { background:#f4f4f5; color:#52525b; border:1px solid #e4e4e7; }

.pill { display:inline-block; font-size:.72rem; font-weight:600; padding:2px 9px; border-radius:999px; border:1px solid; }
.p-tailored { background:#f4f4f5; color:#3f3f46; border-color:#e4e4e7; }
.p-applied  { background:#eff4ff; color:#1849a9; border-color:#b2ccff; }
.p-interview{ background:#fef6e7; color:#92600a; border-color:#fce4a6; }
.p-rejected { background:#fef3f2; color:#b42318; border-color:#fecdca; }
.p-skipped  { background:#f4f4f5; color:#a1a1aa; border-color:#e4e4e7; }

.flag { display:inline-block; font-size:.7rem; color:#52525b; background:#f4f4f5; border:1px solid #e4e4e7;
  border-radius:6px; padding:1px 7px; margin:0 4px 4px 0; }
.detail-h { font-weight:700; font-size:1.15rem; color:#18181b; margin:0 0 2px; }
hr { border:none; border-top:1px solid #ececec; margin:14px 0; }
.stButton button { border-radius:9px; font-weight:500; }
</style>
"""


def score_badge(score: int) -> str:
    cls = "b-green" if score >= 85 else "b-blue" if score >= 70 else "b-gray"
    return f"<span class='badge {cls}'>Match {score}</span>"


def status_pill(status: str) -> str:
    lab = STATUS_LABELS.get(status, status)
    return f"<span class='pill p-{status}'>{lab}</span>"

# ----------------------------- app ----------------------------------------

st.set_page_config(page_title="Job Finder", page_icon="\U0001F4BC", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

if "sel" not in st.session_state:
    st.session_state.sel = None

cnt = counts()

# Header + metrics
st.markdown(
    "<div class='hero-title'>Job Finder</div>"
    "<div class='hero-sub'>Trabajos remotos finanzas + tech, adaptados a tu perfil</div>",
    unsafe_allow_html=True,
)
st.write("")
m = st.columns(4)
metrics = [
    ("Listos para aplicar", cnt.get("tailored", 0)),
    ("Aplicados", cnt.get("applied", 0)),
    ("Entrevistas", cnt.get("interview", 0)),
    (f"Meta semanal", f"{cnt.get('applied',0)}/{WEEKLY_TARGET}"),
]
for col, (lab, num) in zip(m, metrics):
    col.markdown(
        f"<div class='metric-card'><div class='metric-num'>{num}</div>"
        f"<div class='metric-lab'>{lab}</div></div>", unsafe_allow_html=True)

st.write("")

# Sidebar filters
with st.sidebar:
    st.markdown("### Filtros")
    default_status = ["tailored", "applied", "interview"]
    sel_status = st.multiselect(
        "Estado", list(STATUS_LABELS.keys()),
        default=default_status,
        format_func=lambda s: STATUS_LABELS[s],
    )
    min_score = st.slider("Score mínimo", 0, 100, 70, 5)
    query = st.text_input("Buscar", placeholder="título, empresa, skill…")
    st.markdown("---")
    st.caption("Fuentes activas")
    st.caption(", ".join(k for k, v in CFG["sources"].items() if v.get("enabled")))

jobs = load_jobs(tuple(sel_status), min_score, query)

left, right = st.columns([1.05, 1.5], gap="large")

with left:
    st.markdown(f"**{len(jobs)} vacantes**")
    for d in jobs:
        reasons, flags = reasons_of(d)
        sel = st.session_state.sel == d["id"]
        sal = ""
        if d.get("salary_min_usd"):
            hi = f"–{d['salary_max_usd']:,}" if d.get("salary_max_usd") else ""
            sal = f" · ${d['salary_min_usd']:,}{hi} USD"
        st.markdown(
            f"<div class='job-card {'sel' if sel else ''}'>"
            f"<div style='display:flex;justify-content:space-between;gap:8px;align-items:flex-start'>"
            f"<p class='job-title'>{d['title']}</p>{score_badge(d['match_score'])}</div>"
            f"<p class='job-meta'>{d['company']} · {d['location']}{sal}</p>"
            f"<p class='job-reason'>{reasons[:140]}</p>"
            f"<div style='margin-top:8px'>{status_pill(d['status'])}</div>"
            f"</div>", unsafe_allow_html=True)
        if st.button("Ver detalle", key=f"sel{d['id']}", use_container_width=True):
            st.session_state.sel = d["id"]
            st.rerun()

with right:
    sid = st.session_state.sel
    job = next((j for j in jobs if j["id"] == sid), None)
    if not job:
        st.info("Selecciona una vacante a la izquierda para ver el detalle.")
    else:
        reasons, flags = reasons_of(job)
        st.markdown(f"<div class='detail-h'>{job['title']}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<p class='job-meta'>{job['company']} · {job['location']} · "
            f"{job['source']} {score_badge(job['match_score'])}</p>",
            unsafe_allow_html=True)
        if flags:
            st.markdown("".join(f"<span class='flag'>{f}</span>" for f in flags),
                        unsafe_allow_html=True)
        st.markdown(f"<p class='job-reason'>{reasons}</p>", unsafe_allow_html=True)

        a, b = st.columns(2)
        a.link_button("Abrir vacante ↗", job["url"], use_container_width=True)
        pdf = job.get("cv_path", "")
        if pdf and pdf.endswith(".pdf") and Path(pdf).exists():
            b.download_button("Descargar CV (PDF)", Path(pdf).read_bytes(),
                              file_name=Path(pdf).name, mime="application/pdf",
                              use_container_width=True)

        new_status = st.selectbox(
            "Estado", STATUS_ORDER, index=STATUS_ORDER.index(job["status"])
            if job["status"] in STATUS_ORDER else 0,
            format_func=lambda s: STATUS_LABELS[s])
        if new_status != job["status"]:
            if st.button("Guardar estado", type="primary"):
                update_status(job["id"], new_status)
                st.rerun()

        st.markdown("---")
        t_cv, t_cover, t_ans = st.tabs(["CV adaptado", "Carta", "Respuestas"])
        with t_cv:
            cv = read_file(job.get("cv_path"))
            st.markdown(cv if cv else "_No generado._")
        with t_cover:
            cover = read_file(job.get("cover_path"))
            st.markdown(cover if cover else "_No generada._")
        with t_ans:
            ans = read_file(job.get("answers_path"))
            st.markdown(ans if ans else "_No generadas._")
