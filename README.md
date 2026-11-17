# onoma

**Search for what a thing means, not what it is called.**

Every team names things differently: *heart attack* / *MI* / *STEMI*, *k8s* / *Kubernetes*, *HCl* / *muriatic acid* / *ACL*.
Onoma is an open-source search engine with a shared, editable vocabulary. Connect a spreadsheet or table, teach it
your words once, and every search, app and AI agent understands them. Every result explains why it matched.

```
$ onoma search "hydrocloric acid under 40%"
understood “hydrochloric acid” as Hydrochloric acid: 7647-01-0, ACL, HCl, muriatic acid, …
corrected “hydrocloric acid” → “hydrochloric acid”
filter < 40.0%
• Muriatic acid, drum 200 kg  [Parts Stock]
    Concentration = 31% passes “under 40%”
    row says “muriatic acid”, a synonym of Hydrochloric acid · industrial pack
```

## What it does

- **Vocabulary graph.** Meanings (entities) with every name people use: synonyms, abbreviations, codes, units.
  Names can be scoped: *ACL* is hydrochloric acid in the parts stock and a knee ligament in clinical notes.
- **Explained results.** Each hit says which word, which alias and which decision made it match.
- **Query interpretation.** Typos are corrected; `over 60`, `under 40%`, `more than 5 years` become filters.
- **Agents that suggest, people who decide.** The Alias Miner finds `k8s → Kubernetes` and `ReactJS → React` on
  import; the Insights Analyst turns failed searches into fixes. Nothing becomes an alias without a human decision.
- **Rows, not documents.** CSV, TSV, JSON and Excel (every sheet). Column roles are inferred; contact details are
  detected and never stored.
- **Starter packs.** Open medical, tech skills, industrial parts and chemicals, retail (CC-BY-4.0).
- **Meaning search (optional).** With an embedding model configured, rows close in meaning are added after
  vocabulary matches and labelled as such. If the provider is down, search keeps working without it.
- **Share vocabularies.** `onoma export` / `import-pack` (or the Packs screen) move your team's approved names
  between installs, scopes included.
- **Quality you can measure.** `onoma eval` scores search on golden queries and fails CI if quality drops.
- **Sign-in and roles.** `onoma user-add you@team.org --role admin` turns accounts on (scrypt passwords,
  12-hour sessions). Viewer searches, steward decides suggestions and uploads, admin installs packs and manages
  users. The audit log records who did what. With no users it stays open for solo use.
- **Works without an AI model.** Optional providers (Ollama Cloud, OpenAI-compatible, Claude, Gemini) via env vars.

## Run it

Engine (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

```bash
cd engine
uv venv && uv pip install -e ".[dev]"
.venv/bin/onoma demo                 # packs + three sample datasets
.venv/bin/onoma search "heart attack in patients over 60"
.venv/bin/onoma serve                # API on http://127.0.0.1:8000  (docs at /docs)
.venv/bin/python -m pytest           # 18 end-to-end tests
.venv/bin/onoma eval                 # search quality on 17 golden queries (nDCG@10, recall, leaks)
```

Console (Node 20+):

```bash
cd web
npm install
npm run dev                          # http://localhost:3000, talks to NEXT_PUBLIC_ONOMA_API
```

Or everything with Docker: `docker compose up`, then `docker compose exec engine onoma --db /data/onoma.db demo`.

## For AI agents (MCP)

`onoma mcp` runs an MCP server on stdio with three tools: `onoma_search`, `onoma_resolve` and
`onoma_suggest_alias`. Agents search with the same vocabulary people curate; their alias proposals wait in the
review queue and never go live on their own.

```json
{ "mcpServers": { "onoma": { "command": "onoma", "args": ["--db", "/path/to/onoma.db", "mcp"] } } }
```

## Configuration

| Variable | Purpose |
|---|---|
| `ONOMA_DB` | SQLite file (default `onoma.db`) |
| `ONOMA_API_KEYS` | comma-separated keys; when set, every `/v1` call except health needs `X-API-Key` |
| `ONOMA_CORS` | allowed console origins |
| `ONOMA_MODEL_PROVIDER` / `_NAME` / `_URL` / `_KEY` | optional model: `ollama`, `openai`, `anthropic`, `gemini` |
| `ONOMA_EMBED_MODEL` | embedding model for meaning search (ollama, openai or gemini providers) |

## API (v1)

| Method | Path | |
|---|---|---|
| POST | `/v1/search` | hits with `why[]` and `understood` |
| POST | `/v1/resolve` | meanings and names for a term |
| POST | `/v1/datasets` | upload a file |
| GET | `/v1/entities/:id` | a meaning, its names and open suggestions |
| GET | `/v1/suggestions` | review queue cards |
| POST | `/v1/suggestions/:id/decision` | `same` · `different` · `scope` |
| GET | `/v1/insights` | failed searches and stats |
| GET/POST | `/v1/packs` | list and install packs |

## Layout

```
engine/   Python core: storage (SQLite FTS5), vocabulary, ingest, search, agents, API, CLI
web/      Next.js console: Home, Search, Review queue, Vocabulary, Data, Packs, Insights
```

## Roadmap

v0.2 Postgres + pgvector team mode, OIDC sign-in, user management screen.
v1.0 connectors, embeddable search box, relevance test suites in CI, pack registry.

Licence: Apache-2.0.
