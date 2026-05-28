"""Fase 5: scheduler que corre el pipeline solo, a diario.

Uso:
  .venv/bin/python -m src.jobfinder.scheduler          # daemon: corre cada dia
  .venv/bin/python -m src.jobfinder.scheduler --once   # corre una vez y sale

Hora y frecuencia se configuran en config.yaml -> schedule.
Déjalo corriendo en una terminal, o usa cron/launchd apuntando a --once.
"""
from __future__ import annotations

import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from . import pipeline
from .profile import load_config


def _job():
    print("\n######## Corrida programada ########")
    try:
        pipeline.run(do_tailor=True)
    except Exception as e:  # no tumbar el daemon por un fallo de red
        print(f"[scheduler] error en la corrida: {e}")


def main():
    if "--once" in sys.argv:
        pipeline.run(do_tailor=True)
        return

    cfg = load_config().get("schedule", {})
    hour = int(cfg.get("hour", 8))
    minute = int(cfg.get("minute", 0))
    days = cfg.get("days", "*")  # '*' = diario; 'mon-fri'; 'mon' etc.

    sched = BlockingScheduler(timezone=cfg.get("timezone", "America/Monterrey"))
    sched.add_job(_job, "cron", day_of_week=days, hour=hour, minute=minute)
    print(f"[scheduler] activo — corre {days} a las {hour:02d}:{minute:02d} "
          f"({cfg.get('timezone', 'America/Monterrey')}). Ctrl+C para detener.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[scheduler] detenido.")


if __name__ == "__main__":
    main()
