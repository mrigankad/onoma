"""Agents. Each is a small, typed job with a guardrail.

Rules run first and are enough for the MVP. An optional judge model (see models.py)
can re-score candidates, but agents only ever write to `suggestions`; a human decision
is what turns a suggestion into an alias.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from rapidfuzz import fuzz, process

from .db import Database
from .search import Searcher
from .text import contains_phrase, fts_phrase, norm, split_multi
from .vocabulary import Vocabulary

_NUMERONYM = re.compile(r"^([a-z])(\d{1,2})([a-z])$")
_SUFFIXES = (".js", "js", " js", " lang", "lang", " framework")


def _compact(term: str) -> str:
    return re.sub(r"[\s.\-_]", "", term)


def _initials(label: str) -> str:
    return "".join(w[0] for w in re.split(r"[\s\-]+", norm(label).replace(".", " ")) if w)


class AliasMiner:
    """Suggests synonyms found in vocabulary columns. Never approves anything."""

    name = "alias-miner"

    def __init__(self, db: Database, vocab: Vocabulary) -> None:
        self.db = db
        self.vocab = vocab

    def _rejected(self) -> set[tuple[int, str]]:
        return {(r["entity_id"], r["norm_term"]) for r in
                self.db.query("SELECT entity_id, norm_term FROM aliases WHERE status = 'rejected'")}

    def run(self, dataset_id: int | None = None) -> int:
        snap = self.vocab.snapshot()
        known = set(snap.by_term)
        rejected = self._rejected()
        datasets = self.db.query("SELECT * FROM datasets" + (" WHERE id = ?" if dataset_id else ""),
                                 (dataset_id,) if dataset_id else ())
        vocab_terms = [t for t in known if len(t) >= 4]
        compact_index = defaultdict(list)
        for t in known:
            compact_index[_compact(t)].append(t)
        initials_index = defaultdict(set)
        for eid, label in snap.labels.items():
            ini = _initials(label)
            if len(ini) >= 2:
                initials_index[ini].add(eid)

        created = 0
        for ds in datasets:
            vocab_cols = [c["name"] for c in json.loads(ds["columns"]) if c["role"] in ("vocabulary", "title")]
            occurrences: dict[str, list[int]] = defaultdict(list)
            display: dict[str, str] = {}
            neighbours: dict[str, Counter] = defaultdict(Counter)
            for rec in self.db.query("SELECT id, fields FROM records WHERE dataset_id = ?", (ds["id"],)):
                fields = json.loads(rec["fields"])
                row_terms = []
                for col in vocab_cols:
                    for part in split_multi(fields.get(col, "")):
                        n = norm(part)
                        if 2 <= len(n) <= 40:
                            row_terms.append(n)
                            display.setdefault(n, part.strip())
                for n in set(row_terms):
                    occurrences[n].append(rec["id"])
                    for other in row_terms:
                        if other != n and other in known:
                            neighbours[n][other] += 1

            for n, rec_ids in occurrences.items():
                if n in known:
                    continue
                candidates: list[tuple[int, str, float]] = []  # (entity_id, rule, confidence)
                m = _NUMERONYM.match(n)
                if m:
                    first, num, last = m.group(1), int(m.group(2)), m.group(3)
                    for t in known:
                        if len(t) == num + 2 and t[0] == first and t[-1] == last:
                            candidates += [(r.entity_id, f"numeronym: {n} = {t}", 0.93) for r in snap.by_term[t]]
                stripped = n
                for suf in _SUFFIXES:
                    if stripped.endswith(suf) and len(stripped) > len(suf) + 1:
                        stripped = stripped[: -len(suf)].strip()
                for t in compact_index.get(_compact(stripped), []):
                    candidates += [(r.entity_id, f"same word once spacing, dots or a “js” suffix are ignored: {t}", 0.95)
                                   for r in snap.by_term[t]]
                if n.isalpha() and 2 <= len(n) <= 6:
                    for eid in initials_index.get(n, ()):
                        candidates.append((eid, f"initials of “{snap.labels[eid]}”", 0.8))
                if len(n) >= 5 and not candidates:
                    best = process.extractOne(n, vocab_terms, scorer=fuzz.ratio, score_cutoff=88)
                    if best:
                        candidates += [(r.entity_id, f"spelling variant of “{best[0]}” ({best[1]:.0f}% similar)",
                                        round(best[1] / 100 * 0.9, 2)) for r in snap.by_term[best[0]]]
                seen = set()
                for eid, rule, conf in candidates:
                    if eid in seen or (eid, n) in rejected:
                        continue
                    seen.add(eid)
                    near = [t for t, _ in neighbours[n].most_common(4)]
                    evidence = {
                        "rule": rule, "rows": len(rec_ids), "dataset": ds["name"],
                        "sample_record_ids": rec_ids[:2], "appears_next_to": near,
                    }
                    if near:
                        conf = min(0.99, conf + 0.02)
                    created += self._suggest(display.get(n, n), eid, ds["id"], evidence, conf)
        self.db.commit()
        return created

    def _suggest(self, term: str, entity_id: int, scope: int | None, evidence: dict, confidence: float) -> int:
        cur = self.db.execute(
            """INSERT OR IGNORE INTO suggestions (term, norm_term, entity_id, scope_dataset_id, agent,
                                                  evidence, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (term, norm(term), entity_id, scope, self.name, json.dumps(evidence), confidence),
        )
        return cur.rowcount


class InsightsAnalyst:
    """Turns repeated zero-result searches into suggestions, but only ones a dry run proves useful."""

    name = "insights-analyst"

    def __init__(self, db: Database, vocab: Vocabulary, searcher: Searcher) -> None:
        self.db = db
        self.vocab = vocab
        self.searcher = searcher

    def failed_queries(self, limit: int = 50) -> list[dict]:
        rows = self.db.query(
            """SELECT query, COUNT(*) AS times, MAX(created_at) AS last_seen FROM query_log
               WHERE hits = 0 GROUP BY lower(query) ORDER BY times DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]

    def run(self) -> int:
        snap = self.vocab.snapshot()
        terms = [t for t in snap.by_term if len(t) >= 3]
        created = 0
        for fq in self.failed_queries():
            q = norm(fq["query"])
            best = process.extractOne(q, terms, scorer=fuzz.token_set_ratio, score_cutoff=80)
            if not best:
                continue
            target = best[0]
            for ref in snap.by_term[target]:
                dry = self.searcher.search(ref.entity_label, log=False)
                if dry["total"] == 0:
                    continue  # guardrail: only propose fixes that actually return rows
                evidence = {"rule": f"failed search resembles “{target}”", "failed_query": fq["query"],
                            "times": fq["times"], "dry_run_hits": dry["total"]}
                cur = self.db.execute(
                    """INSERT OR IGNORE INTO suggestions (term, norm_term, entity_id, agent, evidence, confidence)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (fq["query"], q, ref.entity_id, self.name, json.dumps(evidence), round(best[1] / 100 * 0.85, 2)),
                )
                created += cur.rowcount
        self.db.commit()
        return created


class ReviewCopilot:
    """Prepares review cards. Cannot decide; only humans click Same / Different / Scope."""

    def __init__(self, db: Database, vocab: Vocabulary) -> None:
        self.db = db
        self.vocab = vocab

    def queue(self, limit: int = 50) -> list[dict]:
        rows = self.db.query(
            """SELECT s.*, e.label AS entity, d.name AS scope_name FROM suggestions s
               LEFT JOIN entities e ON e.id = s.entity_id
               LEFT JOIN datasets d ON d.id = s.scope_dataset_id
               WHERE s.state = 'open' ORDER BY s.confidence DESC, s.id LIMIT ?""",
            (limit,),
        )
        return [self.card(r) for r in rows]

    def card(self, s) -> dict:
        evidence = json.loads(s["evidence"])
        samples = []
        try:
            for r in self.db.query(
                """SELECT r.title, r.fields, d.name AS dataset FROM records_fts f
                   JOIN records r ON r.id = f.rowid JOIN datasets d ON d.id = r.dataset_id
                   WHERE records_fts MATCH ? LIMIT 2""",
                (fts_phrase(s["norm_term"]),),
            ):
                samples.append({"title": r["title"], "dataset": r["dataset"], "fields": json.loads(r["fields"])})
        except Exception:
            pass
        fixes = sum(
            r["c"] for r in self.db.query(
                "SELECT COUNT(*) AS c FROM query_log WHERE hits = 0 AND lower(query) LIKE ?",
                (f"%{s['norm_term']}%",),
            )
        )
        reason = evidence.get("rule", "")
        if evidence.get("rows"):
            reason += f" · seen in {evidence['rows']} rows of {evidence.get('dataset')}"
        if evidence.get("appears_next_to"):
            reason += " · appears next to " + ", ".join(evidence["appears_next_to"][:3])
        return {
            "id": s["id"], "term": s["term"], "entity_id": s["entity_id"], "entity": s["entity"],
            "agent": s["agent"], "confidence": s["confidence"], "scope_dataset_id": s["scope_dataset_id"],
            "scope_name": s["scope_name"], "reason": reason, "evidence": evidence,
            "samples": samples, "fixes_failed_searches": fixes,
        }

    def decide(self, suggestion_id: int, decision: str, actor: str = "user") -> dict:
        if decision not in ("same", "different", "scope"):
            raise ValueError("decision must be same, different or scope")
        s = self.db.one("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,))
        if not s or s["state"] != "open":
            raise KeyError("suggestion not found or already decided")
        entity_id = s["entity_id"]
        if entity_id is None and s["entity_label"]:
            entity_id = self.vocab.upsert_entity(s["entity_label"])
        source = f"agent:{s['agent']}"
        if decision == "different":
            self.vocab.add_alias(entity_id, s["term"], source=source, status="rejected", actor=actor)
        else:
            scope = s["scope_dataset_id"] if decision == "scope" else None
            self.vocab.add_alias(entity_id, s["term"], source=source, scope_dataset_id=scope, actor=actor)
        state = {"same": "same", "different": "different", "scope": "scoped"}[decision]
        self.db.execute("UPDATE suggestions SET state = ? WHERE id = ?", (state, suggestion_id))
        self.db.audit(actor, "suggestion.decided", {"id": suggestion_id, "decision": decision, "term": s["term"]})
        self.db.commit()
        return {"id": suggestion_id, "state": state, "entity_id": entity_id}


def explain_matches(hay: str, terms: list[str]) -> list[str]:
    return [t for t in terms if contains_phrase(hay, norm(t))]
