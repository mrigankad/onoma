"""Command line: onoma demo | import | search | review | serve"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import Onoma


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="onoma", description="Search by meaning.")
    p.add_argument("--db", default=os.getenv("ONOMA_DB", "onoma.db"), help="SQLite file (default onoma.db)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="install starter packs and sample datasets")
    imp = sub.add_parser("import", help="import a CSV, TSV, JSON or XLSX file")
    imp.add_argument("file")
    imp.add_argument("--name")
    s = sub.add_parser("search", help="search and print why each hit matched")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--json", action="store_true")
    sub.add_parser("review", help="list open alias suggestions")
    sub.add_parser("mine", help="run the Alias Miner and Insights Analyst")
    sub.add_parser("mcp", help="run the MCP server on stdio for AI agents")
    ua = sub.add_parser("user-add", help="create an account (the first one turns sign-in on)")
    ua.add_argument("email")
    ua.add_argument("--name", default="")
    ua.add_argument("--role", default="viewer", choices=["viewer", "steward", "admin"])
    ex = sub.add_parser("export", help="write your vocabulary to a pack file")
    ex.add_argument("file")
    ex.add_argument("--all", action="store_true", help="include installed packs")
    ip = sub.add_parser("import-pack", help="install a pack file")
    ip.add_argument("file")
    ev = sub.add_parser("eval", help="score search quality on the golden queries (exit 1 if it drops)")
    ev.add_argument("--min-ndcg", type=float, default=0.85)
    srv = sub.add_parser("serve", help="start the API")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(Onoma(args.db)), host=args.host, port=args.port)
        return 0

    if args.cmd == "eval":
        from .eval import check, run

        report = run()
        for c in report["cases"]:
            flag = "ok " if c["ndcg@10"] >= 0.99 and not c["leaks"] else "!! "
            print(f"{flag}{c['ndcg@10']:.2f}  {c['domain']:<10} {c['query']}")
            for m in c["missing"]:
                print(f"      missing: {m}")
            for leak in c["leaks"]:
                print(f"      leak:    {leak}")
        s = report["summary"]
        print()
        print(f"{s['queries']} queries · nDCG@10 {s['ndcg@10']} · recall {s['recall']} · leaks {s['leaks']}")
        problems = check(report, min_ndcg=args.min_ndcg)
        for p in problems:
            print(f"FAIL {p}")
        return 1 if problems else 0

    eng = Onoma(args.db)
    if args.cmd == "user-add":
        import getpass

        from .auth import Accounts

        pw = os.getenv("ONOMA_NEW_PASSWORD") or getpass.getpass("Password (10+ characters): ")
        u = Accounts(eng.db).create(args.email, args.name, pw, args.role)
        print(f"created {u.email} as {u.role}; sign-in is now required for the API")
        return 0
    if args.cmd == "mcp":
        from .mcp import serve as serve_mcp

        serve_mcp(eng)
        return 0
    if args.cmd == "demo":
        out = eng.load_demo()
        for name, n in out["packs"].items():
            print(f"pack  {name:<12} {n} entities")
        for d in out["datasets"]:
            print(f"data  {d['name']:<22} {d['rows']} rows · {d.get('suggestions_created', 0)} suggestions")
    elif args.cmd == "import":
        path = Path(args.file)
        for d in eng.import_file(path.name, path.read_bytes(), args.name):
            print(f"{d['name']}: {d['added']} added, {d['unchanged']} unchanged, "
                  f"{d.get('suggestions_created', 0)} suggestions")
            for c in d["columns"]:
                print(f"  {c['name']:<24} {c['role']:<11} {c['reason']}")
    elif args.cmd == "search":
        res = eng.search(args.query, limit=args.limit)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0
        u = res["understood"]
        for e in u["entities"]:
            print(f"understood “{e['typed']}” as {e['label']}: {', '.join(e['aliases'])}")
        for c in u["corrections"]:
            print(f"corrected “{c['from']}” → “{c['to']}”")
        for f in u["filters"]:
            print(f"filter {f['op']} {f['value']}{f['unit'] or ''}")
        print(f"{res['total']} results · {res['latency_ms']} ms\n")
        for h in res["hits"]:
            print(f"• {h['title']}  [{h['dataset']}]")
            for w in h["why"]:
                print(f"    {w['text']}")
    elif args.cmd == "export":
        data = eng.vocab.export_pack(include_packs=args.all)
        Path(args.file).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{len(data['entities'])} meanings written to {args.file}")
    elif args.cmd == "import-pack":
        n = eng.vocab.import_pack(json.loads(Path(args.file).read_text(encoding="utf-8")))
        print(f"{n} meanings imported")
    elif args.cmd == "review":
        for c in eng.review.queue():
            print(f"#{c['id']}  {c['term']} → {c['entity']}  ({c['confidence']:.2f})  {c['reason']}")
    elif args.cmd == "mine":
        print(f"alias miner: {eng.miner.run()} new · insights analyst: {eng.insights.run()} new")
    return 0


if __name__ == "__main__":
    sys.exit(main())
