"""Fase 5: pipeline completo de una corrida — agregar -> evaluar -> adaptar.

Uso:
  .venv/bin/python -m src.jobfinder.pipeline            # corrida completa
  .venv/bin/python -m src.jobfinder.pipeline --no-tailor # sin adaptar (mas barato)
"""
from __future__ import annotations

import sys
import time

from . import aggregate, digest, match, tailor


def run(do_tailor: bool = True) -> dict:
    t0 = time.time()
    print("== 1/3 Agregando vacantes ==")
    agg = aggregate.run(verbose=True)

    print("\n== 2/3 Evaluando con IA (solo nuevas) ==")
    mat = match.run(verbose=True)

    tai = {"tailored": 0}
    if do_tailor:
        print("\n== 3/3 Adaptando CV/carta/respuestas (matches nuevos) ==")
        tai = tailor.run(verbose=True)
    else:
        print("\n== 3/3 Omitido (--no-tailor) ==")

    print("\n== Resumen por correo ==")
    try:
        digest.send_if_configured(verbose=True)
    except Exception as e:
        print(f"[pipeline] no se pudo enviar el correo: {e}")

    dt = time.time() - t0
    print(f"\n=== PIPELINE LISTO en {dt:.0f}s ===")
    print(f"Nuevas vacantes: {agg.get('inserted', 0)} | "
          f"Evaluadas: {mat.get('scored', 0)} | "
          f"Nuevos matches: {mat.get('matched', 0)} | "
          f"Adaptadas: {tai.get('tailored', 0)}")
    return {"aggregate": agg, "match": mat, "tailor": tai}


if __name__ == "__main__":
    run(do_tailor="--no-tailor" not in sys.argv)
