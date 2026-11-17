"""The Onoma engine: one object that wires storage, vocabulary, ingest, search and agents."""

from __future__ import annotations

from pathlib import Path

from .agents import AliasMiner, InsightsAnalyst, ReviewCopilot
from .db import Database
from .ingest import Ingestor
from .search import Searcher
from .vectors import Embedder, VectorIndex
from .vocabulary import Vocabulary

DEMO_DIR = Path(__file__).parent / "demo"


class Onoma:
    def __init__(self, path: str | Path = ":memory:", embedder: Embedder | None = None) -> None:
        self.db = Database(path)
        self.vocab = Vocabulary(self.db)
        self.ingestor = Ingestor(self.db)
        if embedder is None:
            from .models import ModelGateway

            embedder = ModelGateway().embedder()
        self.vectors = VectorIndex(self.db, embedder) if embedder else None
        self.searcher = Searcher(self.db, self.vocab, self.vectors)
        self.miner = AliasMiner(self.db, self.vocab)
        self.insights = InsightsAnalyst(self.db, self.vocab, self.searcher)
        self.review = ReviewCopilot(self.db, self.vocab)

    # Event: dataset.indexed -> Alias Miner
    def import_file(self, filename: str, data: bytes, name: str | None = None, mine: bool = True) -> list[dict]:
        results = self.ingestor.import_file(filename, data, name)
        if self.vectors:
            self.vectors.index_missing()
        if mine:
            for r in results:
                r["suggestions_created"] = self.miner.run(r["dataset_id"])
        return results

    def search(self, query: str, datasets: list[int] | None = None, limit: int = 20) -> dict:
        return self.searcher.search(query, datasets, limit)

    def load_demo(self) -> dict:
        """Install the open starter packs and the three sample datasets."""
        packs = {p["id"]: self.vocab.install_pack(p["id"]) for p in self.vocab.available_packs()}
        datasets = []
        for path in sorted(DEMO_DIR.glob("*.csv")):
            datasets += self.import_file(path.name, path.read_bytes(), name=path.stem.replace("_", " ").title())
        # A team decision the demo starts with: in the parts stock, "ACL" is hydrochloric acid
        # (in clinical notes the healthcare pack keeps it as a knee ligament).
        parts = self.db.one("SELECT id FROM datasets WHERE name = 'Parts Stock'")
        acid = self.db.one("SELECT id FROM entities WHERE label = 'Hydrochloric acid'")
        if parts and acid:
            self.vocab.add_alias(acid["id"], "ACL", type="abbr", source="manual",
                                 scope_dataset_id=parts["id"], actor="demo")
            self.db.commit()
        return {"packs": packs, "datasets": datasets}

    def stats(self) -> dict:
        one = lambda sql: self.db.one(sql)[0]  # noqa: E731
        total = one("SELECT COUNT(*) FROM query_log")
        zero = one("SELECT COUNT(*) FROM query_log WHERE hits = 0")
        return {
            "records": one("SELECT COUNT(*) FROM records"),
            "datasets": one("SELECT COUNT(*) FROM datasets"),
            "entities": one("SELECT COUNT(*) FROM entities"),
            "aliases": one("SELECT COUNT(*) FROM aliases WHERE status = 'approved'"),
            "open_suggestions": one("SELECT COUNT(*) FROM suggestions WHERE state = 'open'"),
            "searches": total,
            "zero_result_rate": round(zero / total, 4) if total else None,
            "avg_latency_ms": round(one("SELECT IFNULL(AVG(latency_ms), 0) FROM query_log"), 1),
        }
