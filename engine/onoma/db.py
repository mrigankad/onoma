"""SQLite storage (solo mode).

One file holds records, the vocabulary graph, suggestions and logs.
Postgres (team mode) will implement the same functions later.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS datasets (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  source      TEXT NOT NULL,
  columns     TEXT NOT NULL,            -- JSON: [{name, role}]
  row_count   INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS records (
  id          INTEGER PRIMARY KEY,
  dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  row_hash    TEXT NOT NULL,
  title       TEXT NOT NULL,
  fields      TEXT NOT NULL,            -- JSON object of the original row
  UNIQUE (dataset_id, row_hash)
);

CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
  title, body, content='', contentless_delete=1,
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS entities (
  id          INTEGER PRIMARY KEY,
  label       TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'concept',
  codes       TEXT NOT NULL DEFAULT '{}', -- JSON: {"icd10": "I21"}
  pack        TEXT,
  UNIQUE (label, pack)
);

CREATE TABLE IF NOT EXISTS aliases (
  id          INTEGER PRIMARY KEY,
  entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  term        TEXT NOT NULL,
  norm_term   TEXT NOT NULL,
  type        TEXT NOT NULL DEFAULT 'alias',  -- alias | abbr | code | unit | label
  scope_dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE,
  source      TEXT NOT NULL DEFAULT 'manual', -- manual | pack:<name> | agent:<name>
  status      TEXT NOT NULL DEFAULT 'approved', -- approved | rejected
  decided_by  TEXT,
  decided_at  TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS aliases_unique
  ON aliases (entity_id, norm_term, IFNULL(scope_dataset_id, 0));
CREATE INDEX IF NOT EXISTS aliases_norm ON aliases (norm_term);

CREATE TABLE IF NOT EXISTS suggestions (
  id          INTEGER PRIMARY KEY,
  term        TEXT NOT NULL,
  norm_term   TEXT NOT NULL,
  entity_id   INTEGER REFERENCES entities(id) ON DELETE CASCADE,
  entity_label TEXT,                   -- used when proposing a new entity
  scope_dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE,
  agent       TEXT NOT NULL,
  evidence    TEXT NOT NULL,           -- JSON
  confidence  REAL NOT NULL,
  state       TEXT NOT NULL DEFAULT 'open', -- open | same | different | scoped
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (norm_term, entity_id, entity_label)
);

CREATE TABLE IF NOT EXISTS query_log (
  id          INTEGER PRIMARY KEY,
  query       TEXT NOT NULL,
  structured  TEXT NOT NULL,
  hits        INTEGER NOT NULL,
  latency_ms  REAL NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          INTEGER PRIMARY KEY,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  detail      TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    """Thin wrapper around a SQLite connection. Thread-safe for FastAPI use."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def commit(self) -> None:
        with self.lock:
            self.conn.commit()

    def audit(self, actor: str, action: str, detail: dict) -> None:
        self.execute(
            "INSERT INTO audit_log (actor, action, detail) VALUES (?, ?, ?)",
            (actor, action, json.dumps(detail)),
        )
