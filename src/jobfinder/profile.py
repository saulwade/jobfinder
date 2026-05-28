"""Carga el perfil maestro y el CV base."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_profile() -> dict:
    cfg = load_config()
    return yaml.safe_load((ROOT / cfg["profile"]["master_profile"]).read_text())


def load_master_cv() -> str:
    cfg = load_config()
    return (ROOT / cfg["profile"]["master_cv"]).read_text()


if __name__ == "__main__":
    p = load_profile()
    print(f"Perfil: {p['personal']['full_name']}")
    print(f"Foco: {p['target']['role_focus']}")
    print(f"Titulos objetivo: {len(p['target']['titles'])}")
    print(f"Skills core: {len(p['skills']['core'])}")
    print(f"Experiencias: {len(p['experience'])}")
    print(f"Master CV: {len(load_master_cv())} chars")
