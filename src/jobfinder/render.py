"""Renderiza CV markdown -> HTML imprimible (una hoja) -> PDF vía Chrome headless."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import markdown as md

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# CSS optimizado para UNA hoja Letter, ATS-friendly (sin columnas ni tablas).
PRINT_CSS = """
@page { size: Letter; margin: 0.5in 0.6in; }
* { box-sizing: border-box; }
body {
  font-family: "Calibri", "Helvetica Neue", Arial, sans-serif;
  font-size: 9.6pt; line-height: 1.28; color: #111; margin: 0;
}
h1 { font-size: 16pt; margin: 0 0 2pt; text-align: center; letter-spacing: .3px; }
.contact { text-align: center; font-size: 8.6pt; color: #333; margin-bottom: 6pt; }
h2 {
  font-size: 10pt; text-transform: uppercase; letter-spacing: .5px;
  border-bottom: 1.2px solid #222; padding-bottom: 1pt; margin: 8pt 0 3pt;
}
h3 { font-size: 9.8pt; margin: 4pt 0 0; }
p { margin: 1pt 0; }
ul { margin: 2pt 0 3pt; padding-left: 14pt; }
li { margin: 0.6pt 0; }
em { color: #444; }
a { color: #111; text-decoration: none; }
strong { font-weight: 700; }
"""


def _normalize_md(text: str) -> str:
    """Asegura una línea en blanco antes de cada bloque de lista para que
    markdown la renderice como <ul> y no la pegue al párrafo anterior."""
    out: list[str] = []
    for line in text.splitlines():
        is_item = line.lstrip().startswith(("- ", "* "))
        if is_item and out and out[-1].strip() and not out[-1].lstrip().startswith(("- ", "* ")):
            out.append("")
        out.append(line)
    return "\n".join(out)


def md_to_html(cv_markdown: str) -> str:
    body = md.markdown(_normalize_md(cv_markdown), extensions=["extra"])
    return f"<!doctype html><html><head><meta charset='utf-8'>" \
           f"<style>{PRINT_CSS}</style></head><body>{body}</body></html>"


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    if not Path(CHROME).exists():
        return False
    cmd = [
        CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}", f"file://{html_path}",
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        return pdf_path.exists()
    except (subprocess.SubprocessError, OSError):
        return False


def render_cv(cv_markdown: str, out_base: Path) -> dict:
    """Escribe .md, .html y (si hay Chrome) .pdf. Devuelve rutas creadas."""
    out_base.parent.mkdir(parents=True, exist_ok=True)
    paths = {}
    md_path = out_base.with_suffix(".md")
    md_path.write_text(cv_markdown)
    paths["md"] = str(md_path)

    html_path = out_base.with_suffix(".html")
    html_path.write_text(md_to_html(cv_markdown))
    paths["html"] = str(html_path)

    pdf_path = out_base.with_suffix(".pdf")
    if html_to_pdf(html_path, pdf_path):
        paths["pdf"] = str(pdf_path)
    return paths
