"""MCP server over stdio (JSON-RPC 2.0, one message per line).

Lets AI agents search with the same vocabulary people curate. Tools:
  onoma_search         search rows by meaning, with why each row matched
  onoma_resolve        list the meanings and names of a term
  onoma_suggest_alias  propose a synonym; it goes to the human review queue, never live

Configure in an MCP client, for example:
  {"command": "onoma", "args": ["--db", "/path/onoma.db", "mcp"]}
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import __version__
from .engine import Onoma
from .text import norm

PROTOCOL = "2025-06-18"

TOOLS = [
    {
        "name": "onoma_search",
        "description": "Search the organisation's data by meaning. Understands synonyms, abbreviations, codes, "
                       "typos and filters like 'over 60' or 'under 40%'. Returns rows with a short reason for each.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to find, in plain words"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["query"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "onoma_resolve",
        "description": "Return the meanings a term can have and every name used for each meaning.",
        "inputSchema": {"type": "object", "properties": {"term": {"type": "string"}}, "required": ["term"]},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "onoma_suggest_alias",
        "description": "Propose that a term means an existing meaning. It is queued for human review and is "
                       "not used in search until a person approves it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "meaning": {"type": "string", "description": "Name of an existing meaning, e.g. 'Kubernetes'"},
                "reason": {"type": "string"},
            },
            "required": ["term", "meaning", "reason"],
        },
    },
]


def _text(obj: Any) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False, indent=1)}]}


def call_tool(eng: Onoma, name: str, args: dict) -> dict:
    if name == "onoma_search":
        res = eng.search(str(args["query"])[:500], limit=min(int(args.get("limit", 10)), 50))
        return _text({
            "understood": res["understood"],
            "total": res["total"],
            "hits": [{"title": h["title"], "dataset": h["dataset"], "fields": h["fields"],
                      "why": [w["text"] for w in h["why"]]} for h in res["hits"]],
        })
    if name == "onoma_resolve":
        return _text(eng.searcher.resolve(str(args["term"])[:200]))
    if name == "onoma_suggest_alias":
        term, meaning = str(args["term"])[:120], str(args["meaning"])[:200]
        ent = eng.db.one("SELECT id FROM entities WHERE lower(label) = lower(?)", (meaning,))
        if not ent:
            refs = eng.vocab.snapshot().by_term.get(norm(meaning), [])
            ent = {"id": refs[0].entity_id} if refs else None
        if not ent:
            return {"isError": True, **_text({"error": f"No meaning called '{meaning}'. Use onoma_resolve first."})}
        evidence = {"rule": "proposed by an AI agent", "reason": str(args.get("reason", ""))[:300]}
        cur = eng.db.execute(
            """INSERT OR IGNORE INTO suggestions (term, norm_term, entity_id, agent, evidence, confidence)
               VALUES (?, ?, ?, 'mcp-agent', ?, 0.5)""",
            (term, norm(term), ent["id"], json.dumps(evidence)),
        )
        eng.db.commit()
        return _text({"queued": bool(cur.rowcount), "note": "A person must approve this before it affects search."})
    return {"isError": True, **_text({"error": f"Unknown tool {name}"})}


def handle(eng: Onoma, msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL),
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "onoma", "version": __version__}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            p = msg.get("params", {})
            result = call_tool(eng, p.get("name", ""), p.get("arguments") or {})
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as e:  # never crash the agent's session
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": str(e)}}


def serve(eng: Onoma) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(eng, msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
