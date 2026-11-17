"""Meaning search: embeddings stored next to the rows, searched by cosine similarity.

Optional. Enabled when an embedder is configured (see models.ModelGateway.embedder). Results from
here are labelled "close in meaning" and never presented as a confirmed alias match.
Pure Python on purpose: one SQLite file, no extra services. Fine to ~100k rows; Postgres +
pgvector takes over in team mode.
"""

from __future__ import annotations

import array
import math
from typing import Protocol

from .db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS record_vectors (
  record_id INTEGER PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
  model     TEXT NOT NULL,
  vec       BLOB NOT NULL
);
"""


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _pack(v: list[float]) -> bytes:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return array.array("f", [x / n for x in v]).tobytes()


def _unpack(b: bytes) -> array.array:
    a = array.array("f")
    a.frombytes(b)
    return a


class VectorIndex:
    def __init__(self, db: Database, embedder: Embedder) -> None:
        self.db = db
        self.embedder = embedder
        with db.lock:
            db.conn.executescript(SCHEMA)

    def index_missing(self, batch: int = 64) -> int:
        """Embed every row that has no vector for the current model (idempotent)."""
        rows = self.db.query(
            """SELECT r.id, r.title, r.fields FROM records r
               LEFT JOIN record_vectors v ON v.record_id = r.id AND v.model = ?
               WHERE v.record_id IS NULL""",
            (self.embedder.name,),
        )
        done = 0
        for i in range(0, len(rows), batch):
            chunk = rows[i : i + batch]
            texts = [f"{r['title']}. {r['fields']}"[:2000] for r in chunk]
            vecs = self.embedder.embed(texts)
            for r, v in zip(chunk, vecs):
                self.db.execute("INSERT OR REPLACE INTO record_vectors (record_id, model, vec) VALUES (?, ?, ?)",
                                (r["id"], self.embedder.name, _pack(v)))
            done += len(chunk)
        self.db.commit()
        return done

    def search(self, query: str, k: int = 20, min_score: float = 0.55,
               scope: set[int] | None = None) -> list[tuple[int, float]]:
        q = _unpack(_pack(self.embedder.embed([query])[0]))
        rows = self.db.query(
            """SELECT v.record_id, v.vec, r.dataset_id FROM record_vectors v
               JOIN records r ON r.id = v.record_id WHERE v.model = ?""",
            (self.embedder.name,),
        )
        scored = []
        for r in rows:
            if scope and r["dataset_id"] not in scope:
                continue
            v = _unpack(r["vec"])
            s = sum(a * b for a, b in zip(q, v))
            if s >= min_score:
                scored.append((r["record_id"], s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
