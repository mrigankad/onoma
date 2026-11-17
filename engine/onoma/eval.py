"""Relevance evaluation: golden queries with labelled hits, scored with nDCG@10 and recall.

`onoma eval` loads the demo, runs every golden query and fails (exit 1) when quality drops
below the thresholds, so CI catches a change that makes search worse.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .engine import Onoma

GOLDEN = Path(__file__).parent / "demo" / "golden.json"


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, t in enumerate(ranked[:k]) if t in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 1.0


def run(eng: Onoma | None = None, golden: Path = GOLDEN) -> dict:
    if eng is None:
        eng = Onoma(":memory:")
        eng.load_demo()
    cases = json.loads(golden.read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        res = eng.searcher.search(case["query"], limit=50, log=False)
        ranked = [h["title"] for h in res["hits"]]
        relevant = set(case["relevant"])
        must_not = set(case.get("must_not", []))
        recall = len(relevant & set(ranked)) / len(relevant) if relevant else 1.0
        leaks = sorted(must_not & set(ranked))
        rows.append({
            "query": case["query"], "domain": case["domain"],
            "ndcg@10": round(ndcg_at_k(ranked, relevant), 3), "recall": round(recall, 3),
            "leaks": leaks, "missing": sorted(relevant - set(ranked)),
        })
    n = len(rows)
    summary = {
        "queries": n,
        "ndcg@10": round(sum(r["ndcg@10"] for r in rows) / n, 3),
        "recall": round(sum(r["recall"] for r in rows) / n, 3),
        "leaks": sum(len(r["leaks"]) for r in rows),
    }
    return {"summary": summary, "cases": rows}


def check(report: dict, min_ndcg: float = 0.85, min_recall: float = 0.9) -> list[str]:
    s = report["summary"]
    problems = []
    if s["ndcg@10"] < min_ndcg:
        problems.append(f"nDCG@10 {s['ndcg@10']} < {min_ndcg}")
    if s["recall"] < min_recall:
        problems.append(f"recall {s['recall']} < {min_recall}")
    if s["leaks"]:
        problems.append(f"{s['leaks']} rows matched that must not (scope or meaning leak)")
    return problems
