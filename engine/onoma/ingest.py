"""Ingest service: parse files, infer column roles (Schema Scout rules), index rows."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .db import Database
from .text import is_numeric_value, norm, split_multi

ROLES = ("title", "vocabulary", "number", "text", "personal", "other")

_PERSONAL_HEADER = re.compile(r"phone|mobile|email|e-mail|aadhaar|ssn|passport|dob|birth|address", re.I)
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.\w+")
_PHONE = re.compile(r"^\+?[\d\s\-()•*]{8,}$")
_TITLE_HEADER = re.compile(r"name|title|item|product|description|summary|subject|code desc", re.I)


@dataclass
class ColumnMapping:
    name: str
    role: str
    reason: str


def read_table(filename: str, data: bytes) -> dict[str, list[dict]]:
    """Return {sheet_name: rows}. Supports CSV, TSV, JSON and XLSX."""
    ext = Path(filename).suffix.lower()
    if ext in (".csv", ".tsv", ".txt"):
        text = data.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel_tab if ext == ".tsv" else csv.excel
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
        return {Path(filename).stem: rows}
    if ext == ".json":
        obj = json.loads(data.decode("utf-8"))
        rows = obj if isinstance(obj, list) else obj.get("rows") or [obj]
        return {Path(filename).stem: [r for r in rows if isinstance(r, dict)]}
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets = {}
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            header = next(it, None)
            if not header:
                continue
            cols = [str(h).strip() if h is not None else f"column_{i + 1}" for i, h in enumerate(header)]
            rows = []
            for values in it:
                if values is None or all(v is None or str(v).strip() == "" for v in values):
                    continue
                rows.append({c: ("" if v is None else v) for c, v in zip(cols, values)})
            sheets[ws.title] = rows
        return sheets
    raise ValueError(f"Unsupported file type: {ext or 'none'}. Use CSV, TSV, JSON or XLSX.")


def infer_columns(rows: list[dict], sample: int = 500) -> list[ColumnMapping]:
    """Schema Scout, rules part. Personal data is detected here, locally, before any model call."""
    if not rows:
        return []
    names = list(rows[0].keys())
    sample_rows = rows[:sample]
    mappings: list[ColumnMapping] = []
    title_taken = False
    for name in names:
        values = [str(r.get(name, "")).strip() for r in sample_rows if str(r.get(name, "")).strip()]
        if not values:
            mappings.append(ColumnMapping(name, "other", "empty column"))
            continue
        n = len(values)
        if _PERSONAL_HEADER.search(name) or sum(bool(_EMAIL.search(v) or _PHONE.match(v)) for v in values) / n > 0.5:
            mappings.append(ColumnMapping(name, "personal", "looks like contact or identity data; skipped"))
            continue
        numeric = sum(is_numeric_value(v) for v in values) / n
        avg_len = sum(len(v) for v in values) / n
        distinct = len(set(v.lower() for v in values)) / n
        if numeric >= 0.8:
            mappings.append(ColumnMapping(name, "number", f"{numeric:.0%} numeric values; usable as a filter"))
        elif not title_taken and (_TITLE_HEADER.search(name) or (distinct > 0.9 and 8 <= avg_len <= 120)):
            title_taken = True
            mappings.append(ColumnMapping(name, "title", "distinct short text; shown as the result title"))
        elif avg_len >= 60:
            mappings.append(ColumnMapping(name, "text", f"long text (avg {avg_len:.0f} chars); searched by meaning"))
        else:
            mappings.append(ColumnMapping(name, "vocabulary", "short repeated terms; aliases are mined here"))
    if not title_taken:
        for m in mappings:
            if m.role in ("vocabulary", "text"):
                m.role, m.reason = "title", "first text column; shown as the result title"
                break
    return mappings


class Ingestor:
    def __init__(self, db: Database) -> None:
        self.db = db

    def import_rows(self, name: str, source: str, rows: list[dict],
                    mappings: list[ColumnMapping] | None = None) -> dict:
        mappings = mappings or infer_columns(rows)
        roles = {m.name: m.role for m in mappings}
        title_col = next((m.name for m in mappings if m.role == "title"), None)
        existing = self.db.one("SELECT id FROM datasets WHERE name = ?", (name,))
        cols_json = json.dumps([asdict(m) for m in mappings])
        if existing:
            dataset_id = existing["id"]
            self.db.execute("UPDATE datasets SET columns = ?, source = ? WHERE id = ?", (cols_json, source, dataset_id))
        else:
            dataset_id = self.db.execute(
                "INSERT INTO datasets (name, source, columns) VALUES (?, ?, ?)", (name, source, cols_json)
            ).lastrowid

        added = skipped = 0
        for row in rows:
            kept = {k: v for k, v in row.items() if roles.get(k) != "personal" and str(v).strip() != ""}
            if not kept:
                continue
            row_hash = hashlib.sha1(json.dumps(kept, sort_keys=True, default=str).encode()).hexdigest()
            if self.db.one("SELECT 1 FROM records WHERE dataset_id = ? AND row_hash = ?", (dataset_id, row_hash)):
                skipped += 1
                continue
            title = str(kept.get(title_col) or next(iter(kept.values())))
            body_parts = []
            for k, v in kept.items():
                if roles.get(k) == "vocabulary":
                    body_parts.extend(split_multi(v))
                body_parts.append(str(v))
            record_id = self.db.execute(
                "INSERT INTO records (dataset_id, row_hash, title, fields) VALUES (?, ?, ?, ?)",
                (dataset_id, row_hash, title, json.dumps(kept, default=str)),
            ).lastrowid
            self.db.execute(
                "INSERT INTO records_fts (rowid, title, body) VALUES (?, ?, ?)",
                (record_id, norm(title), norm(" | ".join(body_parts))),
            )
            added += 1
        count = self.db.one("SELECT COUNT(*) AS c FROM records WHERE dataset_id = ?", (dataset_id,))["c"]
        self.db.execute("UPDATE datasets SET row_count = ? WHERE id = ?", (count, dataset_id))
        self.db.audit("system", "dataset.indexed", {"dataset": name, "added": added, "skipped": skipped})
        self.db.commit()
        return {"dataset_id": dataset_id, "name": name, "added": added, "unchanged": skipped,
                "rows": count, "columns": [asdict(m) for m in mappings]}

    def import_file(self, filename: str, data: bytes, name: str | None = None) -> list[dict]:
        sheets = read_table(filename, data)
        results = []
        for sheet, rows in sheets.items():
            ds_name = name or (sheet if len(sheets) > 1 else Path(filename).stem)
            if name and len(sheets) > 1:
                ds_name = f"{name} · {sheet}"
            results.append(self.import_rows(ds_name, filename, rows))
        return results

    def datasets(self) -> list[dict]:
        return [dict(r) | {"columns": json.loads(r["columns"])}
                for r in self.db.query("SELECT * FROM datasets ORDER BY name")]
