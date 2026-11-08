# FilingLens

A research copilot for SEC annual reports (10-K filings), built to answer one question
honestly: **which retrieval and agent techniques actually help, and what do they cost?**

Ask *"Which company owns Helix Vision, and who was that company's CEO in fiscal 2025?"* or
*"How did Northwind's revenue change between 2023 and 2025?"* and get a short answer where
every sentence cites the filing passage it came from. Then run the same question through
seven strategies side by side and read each one's trace.

- **RAG, step by step**: naive vector search → hybrid BM25 + vectors with RRF and
  reranking → **GraphRAG** over an extracted knowledge graph → **agentic RAG** that plans,
  checks its evidence and searches again
- **GenAI patterns**: router, planner–executor, reflection, a calculator tool, structured
  outputs with validation and repair, multi-agent research with a fact-checker
- **MCP, both sides**: an **MCP server** exposing the filing tools to Claude Desktop, VS
  Code or Cursor, and an **MCP client** agent that discovers and calls those tools itself
- **Guardrails**: a planted prompt injection in one filing; sanitising, fencing and
  citation verification stop it
- **Measured**: 112 labelled questions, seven strategies, accuracy, retrieval recall,
  citation precision, faithfulness, injection safety and cost, gated in CI

**Stack:** Python 3.12 · FastAPI · PostgreSQL + pgvector · MCP Python SDK v2 · Angular 18 ·
Docker · GitHub Actions · Playwright

## Results

On the fixture corpus, with the deterministic demo model
([full report](docs/evaluation.md)):

| Strategy | Accuracy | Retrieval recall | Injection-safe | Model calls |
|---|---:|---:|---:|---:|
| Naive RAG | 58.0% | 81.8% | 50% | 1.0 |
| Hybrid + rerank | 89.3% | 99.1% | 50% | 1.0 |
| GraphRAG | 92.9% | 100.0% | 50% | 1.0 |
| Agentic RAG | 93.8% | 100.0% | 100% | 3.1 |
| Router + reflection | 93.8% | 100.0% | 100% | 2.0 |
| Multi-agent | 92.0% | 100.0% | 100% | 5.2 |
| MCP tool agent | 92.9% | 100.0% | 100% | 3.2 |

What the numbers say:
- Hybrid search is the biggest single win, at no extra model cost.
- The graph fixes multi-hop questions (multi-hop accuracy goes from 43% to 86%).
- Only the strategies with guardrails resist the planted injection.
- The router keeps the agent's accuracy at two thirds of its cost.
- More agents is not automatically better.

> The demo model is a deterministic, rule-based stand-in, **not an AI**. It makes the whole
> system run offline and reproducibly in CI. Its numbers measure retrieval and
> orchestration, not answer quality. Run `python -m app.eval.run` with
> `FILINGLENS_LLM_BASE_URL` set to measure a real model.

## How it works

```
                       ┌──────────────── Angular UI ────────────────┐
  Claude Desktop ─MCP─►│ MCP server ─┐   ask · compare · trace      │
                       └─────────────┼────────────┬─────────────────┘
                                     ▼            ▼  /api
              tools: search, financials, graph, sections     strategies
                                     │                 naive · hybrid · graph · agentic
                                     │                 routed · multi_agent · mcp_agent ──MCP──┐
                                     ▼                                │                         │
   EDGAR / fixtures ─► parse Items ─► chunk + context headers ─► embed ─► Postgres + pgvector ◄─┘
                                        └─► extract entities & relations ─► graph tables
                                     model calls ─► LLM Gateway (or the demo model)
```

The decisions behind each part are written up as Architecture Decision Records:

| # | Decision |
|---|---|
| [0001](docs/adr/0001-stack-and-layout.md) | Stack and layout: FastAPI, Postgres + pgvector, Angular, one origin |
| [0002](docs/adr/0002-ingestion.md) | Ingesting 10-Ks: EDGAR client, Item parser, fixture corpus |
| [0003](docs/adr/0003-naive-rag-baseline.md) | Naive RAG baseline: chunking, context headers, citations, demo model |
| [0004](docs/adr/0004-evaluation.md) | Evaluation: labelled set, metrics, CI gate |
| [0005](docs/adr/0005-hybrid-search.md) | Hybrid search: BM25 + vectors, RRF, reranking, query understanding |
| [0006](docs/adr/0006-graphrag.md) | GraphRAG: extraction with provenance, two-hop expansion |
| [0007](docs/adr/0007-agentic-rag.md) | Agentic RAG: planning, re-search, guardrails, citation verification |
| [0008](docs/adr/0008-genai-patterns.md) | Router, reflection and a calculator tool |
| [0009](docs/adr/0009-multi-agent.md) | Multi-agent research: researchers, analyst, fact-checker |
| [0010](docs/adr/0010-mcp-server.md) | The MCP server |
| [0011](docs/adr/0011-mcp-client-agent.md) | An agent that uses tools through MCP |
| [0012](docs/adr/0012-comparison-ui.md) | A UI built for comparing strategies |
| [0013](docs/adr/0013-hardening.md) | Hardening, end-to-end tests and deployment |

## Run it

```bash
docker compose up --build
```

Open http://localhost:8080. It works with no keys at all: fixture filings for three
fictional companies (fiscal 2023–2025), the offline hashing embedder and the demo model.

To use a real model, copy `.env.example` to `.env` and set `FILINGLENS_LLM_BASE_URL`
(ideally the [LLM Gateway](https://github.com/shubhiofficial-17/llm_gateway)). To ingest
real filings, set `FILINGLENS_EDGAR_USER_AGENT` and add a ticker on the Filings page. See
[docs/deploy.md](docs/deploy.md).

## Use it from Claude Desktop (MCP)

Add to `claude_desktop_config.json` (stdio, runs the server from your checkout):

```json
{
  "mcpServers": {
    "filinglens": {
      "command": "/path/to/filing_lens/api/.venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/filing_lens/api"
    }
  }
}
```

Or connect any MCP client to the running stack at `http://localhost:8001/mcp` (streamable
HTTP). Tools: `list_companies`, `search_filings`, `get_section`, `get_financials`,
`compare_companies`, `graph_lookup` and `ask`. There is also a `research_company` prompt
and `filinglens://filing/{ticker}/{fiscal_year}/{item}` resources.

## Develop

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload          # http://localhost:8000/api/docs
pytest                                 # unit, API, MCP; Postgres tests need FILINGLENS_TEST_DATABASE_URL
python -m app.eval.run --markdown ../docs/evaluation.md

cd ../web && npm install && npm start  # http://localhost:4200, proxies /api
npm test

cd ../e2e && npm install && npx playwright test   # against docker compose
```

CI runs three jobs:
- `api`: ruff and pytest, with Postgres + pgvector as a service, then the evaluation with
  its quality gates
- `web`: Karma and a production build
- `e2e`: Docker Compose, a check of the MCP server over HTTP, then Playwright

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/ask` | `{question, strategy, tickers?, years?}` → answer, citations, excerpts, trace, usage |
| GET | `/api/strategies` | the strategies and what each does |
| GET | `/api/filings`, `/api/filings/{id}`, `/api/sections/{id}` | browse the corpus |
| POST | `/api/filings/ingest` | `{ticker, limit}` from EDGAR, or `{source: "fixtures"}` |
| GET | `/api/graph?q=` | entities in `q` and the graph facts around them |
| GET | `/api/eval/report` | the latest evaluation report |
| GET | `/api/health`, `/api/health/ready` | liveness; readiness (Postgres and pgvector) |

## Repository layout

```
api/app/
  ingest/     EDGAR client, 10-K parser, ingestion          fixtures/  the fictional corpus
  rag/        chunking, embeddings, BM25, hybrid retrieval, prompts, answers, pipelines
  graph/      entity/relation extraction and graph retrieval
  agents/     agentic RAG, router/reflection/calculator, multi-agent, structured outputs
  mcp/        tools, MCP server, MCP client, tool-using agent
  eval/       labelled questions, metrics, runner, thresholds, latest report
  llm/        OpenAI-compatible client and the demo model     store/  in-memory and Postgres
web/          Angular app and nginx config      e2e/  Playwright      docs/  ADRs, evaluation, deploy
```

## Licence

MIT
