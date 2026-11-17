"""Query service: interpret -> correct -> expand via vocabulary -> retrieve -> rank -> explain.

Deterministic and fast. The only "agent" here (Query Interpreter) runs as rules; a model
can be plugged in later behind a strict timeout, but search never depends on it.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from .db import Database
from .text import STOPWORDS, contains_phrase, fts_phrase, ngrams, norm, term_in, to_number, type_phrase
from .vocabulary import AliasRef, Vocabulary

_GT = r"over|above|more than|greater than|older than|at least|min(?:imum)?|>=|>"
_LT = r"under|below|less than|younger than|at most|max(?:imum)?|<=|<"
_FILTER = re.compile(
    rf"(?P<op>{_GT}|{_LT})\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|pct|years?|yrs?|y)?(?![\w])",
    re.I,
)
_HINTS = {
    "age": ("patient", "patients", "aged", "age", "people", "adults"),
    "exp": ("experience", "exp", "senior", "engineers", "developers", "candidates"),
}


@dataclass
class NumericFilter:
    op: str
    value: float
    unit: str | None
    hint: str | None
    text: str

    def check(self, fields: dict, number_columns: list[str]) -> tuple[bool, str | None]:
        cols = self._target_columns(number_columns, fields)
        for col in cols:
            v = to_number(fields.get(col, ""))
            if v is None:
                continue
            ok = v > self.value if self.op == ">" else v < self.value
            if ok:
                return True, col
        return (not cols), None  # no numeric column in this dataset -> filter doesn't apply

    def _target_columns(self, number_columns: list[str], fields: dict) -> list[str]:
        cols = [c for c in number_columns if c in fields]
        if self.unit == "%":
            # Only columns that hold percentages; a dataset without one is not filtered.
            return [c for c in cols if "%" in str(fields.get(c, "")) or re.search(r"conc|%|percent|strength|purity", c, re.I)]
        if self.hint == "age":
            return [c for c in cols if re.search(r"\bage\b|years? old", c, re.I)] or cols
        if self.hint == "exp" or (self.unit or "").startswith("y"):
            return [c for c in cols if re.search(r"exp|year|yrs", c, re.I)] or cols
        return cols


@dataclass
class EntityGroup:
    entity_id: int
    label: str
    matched_term: str
    match_type: str
    terms: dict[str, AliasRef] = field(default_factory=dict)
    sense_note: str | None = None


class Searcher:
    def __init__(self, db: Database, vocab: Vocabulary, vectors=None) -> None:
        self.db = db
        self.vocab = vocab
        self.vectors = vectors

    # ---------- interpret ----------

    def _interpret(self, raw: str) -> tuple[str, list[NumericFilter]]:
        filters = []
        text = raw
        for m in _FILTER.finditer(raw):
            before = norm(raw[: m.start()]).split(" ")[-3:]
            hint = next((h for h, words in _HINTS.items() if any(w in words for w in before)), None)
            unit = m.group("unit")
            if unit and unit.lower() in ("percent", "pct"):
                unit = "%"
            op = ">" if re.fullmatch(_GT, m.group("op"), re.I) else "<"
            filters.append(NumericFilter(op, float(m.group("num")), unit and unit.lower(), hint, m.group(0).strip()))
            text = text.replace(m.group(0), " ")
        return text, filters

    # ---------- correct + expand ----------

    def _match_entities(self, words: list[str], scope: set[int] | None) -> tuple[list[EntityGroup], list[str], list[dict]]:
        snap = self.vocab.snapshot()
        used = [False] * len(words)
        groups: dict[int, EntityGroup] = {}
        corrections: list[dict] = []

        def allowed(ref: AliasRef) -> bool:
            return ref.scope_dataset_id is None or scope is None or ref.scope_dataset_id in scope

        def take(i: int, j: int, phrase: str, refs: list[AliasRef], match_type: str) -> None:
            refs = [r for r in refs if allowed(r)]
            if not refs:
                return
            # Sense Resolver: when specific datasets are searched, a meaning scoped to them wins.
            # When searching everything, keep every meaning; each row is judged by its own dataset.
            scoped = [r for r in refs if r.scope_dataset_id is not None]
            chosen = scoped if (scope and scoped) else refs
            entity_ids = sorted({r.entity_id for r in chosen})
            note = None
            if len(entity_ids) > 1:
                labels = " / ".join(snap.labels[e] for e in entity_ids)
                note = f"“{phrase}” has several meanings ({labels}); each row uses its dataset’s meaning"
            for eid in entity_ids:
                g = groups.get(eid)
                if not g:
                    g = groups[eid] = EntityGroup(eid, snap.labels[eid], phrase, match_type, sense_note=note)
                    for ref in snap.by_entity.get(eid, []):
                        if allowed(ref):
                            g.terms[norm(ref.term)] = ref
            for k in range(i, j):
                used[k] = True

        for i, j, phrase in ngrams(words, snap.max_words):
            if any(used[i:j]) or (j - i == 1 and phrase in STOPWORDS):
                continue
            if phrase in snap.by_term:
                take(i, j, phrase, snap.by_term[phrase], "exact")

        # Typo correction against vocabulary terms (only for still-unmatched words).
        vocab_terms = [t for t in snap.by_term if len(t) >= 5]
        if vocab_terms:
            for i, j, phrase in ngrams(words, 3):
                if any(used[i:j]) or len(phrase) < 5 or phrase in STOPWORDS:
                    continue
                best = process.extractOne(phrase, vocab_terms, scorer=fuzz.ratio, score_cutoff=87)
                if best and abs(len(best[0]) - len(phrase)) <= 3:
                    corrections.append({"from": phrase, "to": best[0], "score": round(best[1])})
                    take(i, j, best[0], snap.by_term[best[0]], "typo")

        leftovers = [w for k, w in enumerate(words) if not used[k] and w not in STOPWORDS and len(w) > 1]
        return list(groups.values()), leftovers, corrections

    # ---------- retrieve ----------

    def _fts(self, match: str, limit: int) -> list[sqlite3.Row]:
        try:
            return self.db.query(
                """SELECT rowid AS id, bm25(records_fts, 4.0, 1.0) AS bm25
                   FROM records_fts WHERE records_fts MATCH ? ORDER BY bm25 LIMIT ?""",
                (match, limit),
            )
        except sqlite3.OperationalError:
            return []

    def search(self, raw: str, datasets: list[int] | None = None, limit: int = 20, log: bool = True) -> dict:
        t0 = time.perf_counter()
        scope = set(datasets) if datasets else None
        text, filters = self._interpret(raw)
        words = norm(text).split(" ") if norm(text) else []
        groups, leftovers, corrections = self._match_entities(words, scope)

        by_phrase: dict[str, list[EntityGroup]] = {}
        if groups:
            # Entities sharing the same typed phrase are alternative meanings -> OR them together.
            for g in groups:
                by_phrase.setdefault(g.matched_term, []).append(g)
            clauses = []
            for gs in by_phrase.values():
                terms = {t for g in gs for t in g.terms}
                terms |= {t.replace(" ", "") for t in terms if " " in t and any(c.isdigit() for c in t)}
                clauses.append("(" + " OR ".join(fts_phrase(t) for t in sorted(terms)) + ")")
            match = " AND ".join(clauses)
        elif leftovers:
            match = " OR ".join(f"{w}*" if len(w) >= 3 else fts_phrase(w) for w in leftovers)
        else:
            match = ""

        candidates = self._fts(match, 500) if match else []
        ds_rows = {r["id"]: r for r in self.db.query("SELECT id, name, columns FROM datasets")}
        number_cols = {
            did: [c["name"] for c in json.loads(r["columns"]) if c["role"] == "number"] for did, r in ds_rows.items()
        }

        hits = []
        if candidates:
            ids = [c["id"] for c in candidates]
            bm = {c["id"]: c["bm25"] for c in candidates}
            placeholders = ",".join("?" * len(ids))
            recs = self.db.query(f"SELECT * FROM records WHERE id IN ({placeholders})", tuple(ids))
            for rec in recs:
                if scope and rec["dataset_id"] not in scope:
                    continue
                fields = json.loads(rec["fields"])
                hay = norm(rec["title"] + " | " + " | ".join(str(v) for v in fields.values()))
                hay_tokens = set(hay.split(" "))
                ds_id = rec["dataset_id"]

                # Which meaning applies to this row? A scoped alias only counts in its own dataset,
                # and for the same typed phrase it beats a global meaning.
                row_matches: list[tuple[EntityGroup, str, AliasRef]] = []
                complete = True
                for phrase, gs in by_phrase.items() if groups else []:
                    found = []
                    for g in gs:
                        valid = [t for t, r in g.terms.items()
                                 if (r.scope_dataset_id in (None, ds_id)) and term_in(hay, hay_tokens, t)]
                        if valid:
                            t = max(valid, key=len)
                            found.append((g, t, g.terms[t]))
                    if any(r.scope_dataset_id == ds_id for _, _, r in found):
                        found = [f for f in found if f[2].scope_dataset_id == ds_id]
                    if not found:
                        complete = False
                        break
                    row_matches.extend(found)
                if not complete:
                    continue
                why: list[dict] = []
                passed = True
                for f in filters:
                    ok, col = f.check(fields, number_cols.get(rec["dataset_id"], []))
                    if not ok:
                        passed = False
                        break
                    if col:
                        why.append({"step": "filter", "text": f"{col} = {fields[col]} passes “{f.text}”"})
                if not passed:
                    continue
                matched_via = None
                for g, term, ref in row_matches:
                    exact = term == norm(g.matched_term) and g.match_type == "exact"
                    kind = "exact words" if exact else ref.type
                    src = ref.source.replace("pack:", "").replace("_", " ") + " pack" if ref.source.startswith("pack:") else (
                        "team decision" if ref.source in ("manual", "demo") else ref.source)
                    via = {"term": ref.term, "type": kind, "source": src, "entity": g.label,
                           "entity_id": g.entity_id, "scoped": ref.scope_dataset_id is not None}
                    matched_via = matched_via or via
                    if g.match_type == "typo":
                        why.append({"step": "typo", "text": f"spelling corrected to “{g.matched_term}”"})
                    why.append({"step": "entity", "text": f"“{g.matched_term}” means {g.label}"})
                    if not exact:
                        scope_txt = ", only in this dataset" if via["scoped"] else ""
                        why.append({"step": "alias",
                                    "text": f"row says “{ref.term}”, {type_phrase(ref.type)} of {g.label} · {src}{scope_txt}"})
                bonus = sum(1.5 for w in leftovers if contains_phrase(hay, w))
                bonus += 1.0 if matched_via and contains_phrase(norm(rec["title"]), norm(matched_via["term"])) else 0
                score = -bm[rec["id"]] + bonus
                if not groups:
                    found = [w for w in leftovers if w in hay]
                    why.append({"step": "keyword", "text": "keyword match: " + ", ".join(found or leftovers)})
                hits.append({
                    "record_id": rec["id"], "dataset_id": rec["dataset_id"],
                    "dataset": ds_rows[rec["dataset_id"]]["name"], "title": rec["title"],
                    "fields": fields, "score": round(score, 3), "matched_via": matched_via, "why": why,
                })
        if self.vectors and words:
            hits += self._meaning_hits(" ".join(words), {h["record_id"] for h in hits}, filters, scope,
                                       ds_rows, number_cols)
        did_you_mean: list[dict] = []
        if not hits and words:
            hits, did_you_mean = self._near_meaning(" ".join(words), leftovers, scope, ds_rows)
        hits.sort(key=lambda h: h["score"], reverse=True)
        latency = (time.perf_counter() - t0) * 1000
        understood = {
            "entities": [
                {"id": g.entity_id, "label": g.label, "typed": g.matched_term, "match": g.match_type,
                 "aliases": sorted({r.term for r in g.terms.values()}), "note": g.sense_note}
                for g in groups
            ],
            "filters": [{"op": f.op, "value": f.value, "unit": f.unit, "text": f.text} for f in filters],
            "corrections": corrections,
            "keywords": leftovers,
            "did_you_mean": did_you_mean,
        }
        if log:
            self.db.execute(
                "INSERT INTO query_log (query, structured, hits, latency_ms) VALUES (?, ?, ?, ?)",
                (raw, json.dumps(understood), len(hits), latency),
            )
            self.db.commit()
        return {"query": raw, "understood": understood, "total": len(hits), "hits": hits[:limit],
                "latency_ms": round(latency, 1)}

    def _meaning_hits(self, phrase: str, seen: set[int], filters, scope, ds_rows, number_cols) -> list[dict]:
        """Rows close in meaning that no alias reached. Ranked below every alias match."""
        out = []
        try:
            found = self.vectors.search(phrase, k=20, scope=scope)
        except Exception:
            return out  # a provider outage degrades to keyword + vocabulary search
        for rid, sim in found:
            if rid in seen:
                continue
            rec = self.db.one("SELECT * FROM records WHERE id = ?", (rid,))
            fields = json.loads(rec["fields"])
            why = []
            ok = True
            for f in filters:
                passed, col = f.check(fields, number_cols.get(rec["dataset_id"], []))
                if not passed:
                    ok = False
                    break
                if col:
                    why.append({"step": "filter", "text": f"{col} = {fields[col]} passes “{f.text}”"})
            if not ok:
                continue
            why.append({"step": "meaning", "text": f"close in meaning ({sim:.2f}); no alias links it yet"})
            out.append({"record_id": rid, "dataset_id": rec["dataset_id"], "dataset": ds_rows[rec["dataset_id"]]["name"],
                        "title": rec["title"], "fields": fields, "score": round(sim - 100, 3),
                        "matched_via": None, "why": why})
        return out

    def _near_meaning(self, phrase: str, leftovers: list[str], scope: set[int] | None,
                      ds_rows: dict) -> tuple[list[dict], list[dict]]:
        """No match at all: offer close vocabulary terms and rows with similar wording.

        Rows found this way are labelled as similar wording, never as a confirmed meaning.
        """
        snap = self.vocab.snapshot()
        suggestions = []
        for term, score, _ in process.extract(phrase, list(snap.by_term), scorer=fuzz.WRatio, limit=3, score_cutoff=80):
            ref = snap.by_term[term][0]
            suggestions.append({"term": ref.term, "meaning": ref.entity_label, "score": round(score)})
        rows = self.db.query("SELECT id, dataset_id, title, fields FROM records LIMIT 5000")
        titles = {r["id"]: norm(r["title"]) for r in rows if not scope or r["dataset_id"] in scope}
        hits = []
        if leftovers:
            for rid_title, score, rid in process.extract(phrase, titles, scorer=fuzz.token_set_ratio,
                                                         limit=5, score_cutoff=70):
                r = next(x for x in rows if x["id"] == rid)
                hits.append({
                    "record_id": r["id"], "dataset_id": r["dataset_id"], "dataset": ds_rows[r["dataset_id"]]["name"],
                    "title": r["title"], "fields": json.loads(r["fields"]), "score": round(score / 100, 3),
                    "matched_via": None,
                    "why": [{"step": "keyword", "text": f"similar wording ({score:.0f}% match), not a known meaning"}],
                })
        return hits, suggestions

    def resolve(self, term: str) -> list[dict]:
        snap = self.vocab.snapshot()
        refs = snap.by_term.get(norm(term), [])
        out = {}
        for r in refs:
            out[r.entity_id] = {"entity_id": r.entity_id, "label": r.entity_label,
                                "aliases": sorted({a.term for a in snap.by_entity[r.entity_id]})}
        return list(out.values())
