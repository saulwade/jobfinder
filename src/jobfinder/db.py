"""SQLite local: esquema y helpers. Cero config."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    external_id     TEXT,                 -- id en la fuente original
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT,
    location        TEXT,
    remote          INTEGER DEFAULT 1,
    salary_text     TEXT,
    salary_min_usd  INTEGER,
    salary_max_usd  INTEGER,
    description     TEXT,
    tags            TEXT,                 -- csv
    posted_at       TEXT,
    fetched_at      TEXT DEFAULT (datetime('now')),
    fingerprint     TEXT UNIQUE,          -- dedupe: hash(title+company)
    -- matching
    match_score     INTEGER,             -- 0-100
    match_reasons   TEXT,
    match_at        TEXT,
    -- application pipeline
    status          TEXT DEFAULT 'new',  -- new|matched|tailored|applied|interview|rejected|skipped
    cv_path         TEXT,
    cover_path      TEXT,
    answers_path    TEXT,
    notes           TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score  ON jobs(match_score);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    import yaml

    root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((root / "config.yaml").read_text())
    path = root / cfg["database"]["path"]
    init_db(path)
    print(f"DB lista en {path}")
