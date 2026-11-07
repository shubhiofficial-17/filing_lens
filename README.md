# FilingLens

A research copilot for SEC annual reports (10-K filings). Ask questions like *"How did
Microsoft describe AI-related risks in its last three 10-Ks?"* and get answers with
citations to the exact sections.

The project is a step-by-step comparison of retrieval and agent techniques, each one
measured on the same labelled question set:

- naive RAG → hybrid search (BM25 + vectors) with reranking → GraphRAG → agentic RAG
- GenAI patterns: model routing, planner–executor, reflection, multi-agent research
- an **MCP server**, so the same tools work from Claude Desktop, VS Code or Cursor

**Stack:** Python · FastAPI · PostgreSQL + pgvector · Angular 18 · Docker · GitHub Actions

## Status

| # | Milestone | Status |
|---|---|---|
| 1 | Skeleton: API, web, Postgres + pgvector, Docker, CI | ✅ |
| 2 | Ingest 10-K filings from SEC EDGAR | ⏳ |
| 3 | Naive RAG with citations (baseline) | |
| 4 | Evaluation harness | |
| 5 | Hybrid search and reranking | |
| 6 | GraphRAG | |
| 7 | Agentic RAG | |
| 8 | GenAI patterns: routing, planner–executor, reflection | |
| 9 | Multi-agent research | |
| 10 | MCP server | |
| 11 | MCP client | |
| 12 | Comparison UI | |
| 13 | Hardening and E2E tests | |

## Run it

```bash
docker compose up --build
```

Open http://localhost:8080. The header shows whether the API and database are ready.

## Develop

API (Python 3.12+), with a local Postgres from `docker compose up db`:

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export FILINGLENS_DATABASE_URL=postgresql://filinglens:filinglens@localhost:5432/filinglens
uvicorn app.main:app --reload
pytest
```

The database port isn't published by default; add `ports: ["5432:5432"]` to the `db`
service for local development. API docs are at http://localhost:8000/api/docs.

Web (Node 20):

```bash
cd web
npm install
npm start        # http://localhost:4200, proxies /api to :8000
npm test
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness, never touches the database |
| GET | `/api/health/ready` | 200 when Postgres answers and pgvector is enabled, otherwise 503 |

## Decisions

Architecture Decision Records are in [`docs/adr`](docs/adr).

## Licence

MIT
