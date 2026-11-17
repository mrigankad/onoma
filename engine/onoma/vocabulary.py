"""Vocabulary service: entities, aliases, scopes, packs and decisions.

This is the source of truth. Agents never write here directly; they write
suggestions, and a human decision turns a suggestion into an alias.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .db import Database
from .text import norm

PACKS_DIR = Path(__file__).parent / "packs"


@dataclass
class AliasRef:
    entity_id: int
    entity_label: str
    term: str
    type: str
    source: str
    scope_dataset_id: int | None


@dataclass
class Snapshot:
    """In-memory lookup used on the search hot path. Rebuilt on every change."""

    by_term: dict[str, list[AliasRef]] = field(default_factory=dict)
    by_entity: dict[int, list[AliasRef]] = field(default_factory=dict)
    labels: dict[int, str] = field(default_factory=dict)
    max_words: int = 1


class Vocabulary:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._snapshot: Snapshot | None = None

    # ---------- reads ----------

    def snapshot(self) -> Snapshot:
        if self._snapshot is None:
            self._snapshot = self._build_snapshot()
        return self._snapshot

    def invalidate(self) -> None:
        self._snapshot = None

    def _build_snapshot(self) -> Snapshot:
        snap = Snapshot()
        rows = self.db.query(
            """SELECT a.entity_id, e.label, a.term, a.norm_term, a.type, a.source,
                      a.scope_dataset_id
               FROM aliases a JOIN entities e ON e.id = a.entity_id
               WHERE a.status = 'approved'"""
        )
        for r in rows:
            ref = AliasRef(r["entity_id"], r["label"], r["term"], r["type"], r["source"],
                           r["scope_dataset_id"])
            snap.by_term.setdefault(r["norm_term"], []).append(ref)
            snap.by_entity.setdefault(r["entity_id"], []).append(ref)
            snap.labels[r["entity_id"]] = r["label"]
            snap.max_words = max(snap.max_words, len(r["norm_term"].split(" ")))
        return snap

    def entity(self, entity_id: int) -> dict | None:
        e = self.db.one("SELECT * FROM entities WHERE id = ?", (entity_id,))
        if not e:
            return None
        aliases = self.db.query(
            """SELECT a.*, d.name AS scope_name FROM aliases a
               LEFT JOIN datasets d ON d.id = a.scope_dataset_id
               WHERE a.entity_id = ? ORDER BY a.status, a.type, a.term""",
            (entity_id,),
        )
        open_suggestions = self.db.query(
            "SELECT * FROM suggestions WHERE entity_id = ? AND state = 'open'", (entity_id,)
        )
        return {
            "id": e["id"],
            "label": e["label"],
            "kind": e["kind"],
            "codes": json.loads(e["codes"]),
            "pack": e["pack"],
            "aliases": [
                {
                    "id": a["id"], "term": a["term"], "type": a["type"], "source": a["source"],
                    "status": a["status"], "scope": a["scope_name"],
                    "decided_by": a["decided_by"], "decided_at": a["decided_at"],
                }
                for a in aliases
            ],
            "suggestions": [dict(s) | {"evidence": json.loads(s["evidence"])} for s in open_suggestions],
        }

    def list_entities(self, q: str = "", limit: int = 50) -> list[dict]:
        like = f"%{norm(q)}%"
        rows = self.db.query(
            """SELECT e.id, e.label, e.kind, e.pack,
                      SUM(a.status = 'approved') AS alias_count
               FROM entities e LEFT JOIN aliases a ON a.entity_id = e.id
               WHERE ? = '%%' OR e.id IN (SELECT entity_id FROM aliases WHERE norm_term LIKE ?)
               GROUP BY e.id ORDER BY e.label LIMIT ?""",
            (like, like, limit),
        )
        return [dict(r) for r in rows]

    # ---------- writes ----------

    def upsert_entity(self, label: str, kind: str = "concept", codes: dict | None = None,
                      pack: str | None = None) -> int:
        row = self.db.one(
            "SELECT id FROM entities WHERE label = ? AND IFNULL(pack, '') = IFNULL(?, '')",
            (label, pack),
        )
        if row:
            return row["id"]
        cur = self.db.execute(
            "INSERT INTO entities (label, kind, codes, pack) VALUES (?, ?, ?, ?)",
            (label, kind, json.dumps(codes or {}), pack),
        )
        entity_id = cur.lastrowid
        self.add_alias(entity_id, label, type="label", source=f"pack:{pack}" if pack else "manual")
        return entity_id

    def add_alias(self, entity_id: int, term: str, type: str = "alias", source: str = "manual",
                  scope_dataset_id: int | None = None, status: str = "approved",
                  actor: str = "system") -> int | None:
        n = norm(term)
        if not n:
            return None
        existing = self.db.one(
            """SELECT id FROM aliases WHERE entity_id = ? AND norm_term = ?
               AND IFNULL(scope_dataset_id, 0) = IFNULL(?, 0)""",
            (entity_id, n, scope_dataset_id),
        )
        if existing:
            self.db.execute(
                "UPDATE aliases SET status = ?, decided_by = ?, decided_at = datetime('now') WHERE id = ?",
                (status, actor, existing["id"]),
            )
            alias_id = existing["id"]
        else:
            cur = self.db.execute(
                """INSERT INTO aliases (entity_id, term, norm_term, type, scope_dataset_id, source,
                                        status, decided_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (entity_id, term, n, type, scope_dataset_id, source, status, actor),
            )
            alias_id = cur.lastrowid
        self.db.audit(actor, "alias.set", {"entity_id": entity_id, "term": term, "status": status,
                                           "scope_dataset_id": scope_dataset_id})
        self.invalidate()
        return alias_id

    def remove_alias(self, alias_id: int, actor: str = "system") -> None:
        row = self.db.one("SELECT * FROM aliases WHERE id = ?", (alias_id,))
        if row:
            self.db.execute("DELETE FROM aliases WHERE id = ?", (alias_id,))
            self.db.audit(actor, "alias.removed", dict(row))
            self.invalidate()

    # ---------- packs ----------

    @staticmethod
    def available_packs() -> list[dict]:
        packs = []
        for path in sorted(PACKS_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            packs.append({
                "id": path.stem, "name": data["name"], "description": data.get("description", ""),
                "license": data.get("license", ""), "entities": len(data["entities"]),
            })
        return packs

    def installed_packs(self) -> set[str]:
        return {r["pack"] for r in self.db.query("SELECT DISTINCT pack FROM entities WHERE pack IS NOT NULL")}

    def export_pack(self, name: str = "My vocabulary", include_packs: bool = False) -> dict:
        """Approved vocabulary as a pack file. By default only what this team added or changed."""
        out = []
        for e in self.db.query("SELECT * FROM entities ORDER BY label"):
            aliases = self.db.query(
                """SELECT a.term, a.type, a.source, d.name AS scope FROM aliases a
                   LEFT JOIN datasets d ON d.id = a.scope_dataset_id
                   WHERE a.entity_id = ? AND a.status = 'approved' AND a.type != 'label'""",
                (e["id"],),
            )
            mine = [a for a in aliases if include_packs or not a["source"].startswith("pack:")]
            if not mine and (e["pack"] and not include_packs):
                continue
            entry = {"label": e["label"], "kind": e["kind"], "codes": json.loads(e["codes"]),
                     "aliases": [{"term": a["term"], "type": a["type"], **({"scope": a["scope"]} if a["scope"] else {})}
                                 for a in mine]}
            out.append(entry)
        return {"name": name, "description": "Exported from Onoma", "license": "CC-BY-4.0", "entities": out}

    def import_pack(self, data: dict, actor: str = "user") -> int:
        """Install a pack given as a dict (same format as the bundled packs)."""
        if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
            raise ValueError("Not an Onoma pack: expected {name, entities: [...]}")
        pack_id = "import:" + str(data.get("name", "pack"))[:60]
        count = 0
        for ent in data["entities"][:50000]:
            label = str(ent.get("label", "")).strip()
            if not label:
                continue
            eid = self.upsert_entity(label, ent.get("kind", "concept"), ent.get("codes"), None)
            for a in ent.get("aliases", []):
                term, typ, scope = (a, "alias", None) if isinstance(a, str) else (a.get("term", ""), a.get("type", "alias"), a.get("scope"))
                scope_id = None
                if scope:
                    row = self.db.one("SELECT id FROM datasets WHERE name = ?", (scope,))
                    scope_id = row["id"] if row else None
                    if not row:
                        continue  # scoped to a dataset this install doesn't have
                self.add_alias(eid, term, type=typ, source=pack_id, scope_dataset_id=scope_id, actor=actor)
            count += 1
        self.db.audit(actor, "pack.imported", {"pack": pack_id, "entities": count})
        self.db.commit()
        return count

    def install_pack(self, pack_id: str, actor: str = "system") -> int:
        path = PACKS_DIR / f"{pack_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown pack: {pack_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for ent in data["entities"]:
            eid = self.upsert_entity(ent["label"], ent.get("kind", "concept"), ent.get("codes"), pack_id)
            for code_value in (ent.get("codes") or {}).values():
                self.add_alias(eid, code_value, type="code", source=f"pack:{pack_id}", actor=actor)
            for a in ent.get("aliases", []):
                term, typ = (a, "alias") if isinstance(a, str) else (a["term"], a.get("type", "alias"))
                self.add_alias(eid, term, type=typ, source=f"pack:{pack_id}", actor=actor)
            count += 1
        self.db.audit(actor, "pack.installed", {"pack": pack_id, "entities": count})
        self.db.commit()
        return count
