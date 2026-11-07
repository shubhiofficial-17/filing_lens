# 0001. Stack and repository layout

Date: 2026-11-07
Status: accepted

## Context

FilingLens answers questions about SEC annual reports (10-K filings). Later milestones add
hybrid retrieval, a knowledge graph, agents and an MCP server, and every technique is
measured on a labelled question set. The first milestone only needs a deployable skeleton,
but the choices made here shape everything after it.

## Decision

- **API in Python with FastAPI.** The retrieval, evaluation and MCP ecosystems are strongest
  in Python (the official MCP SDK, rerankers, embedding libraries). FastAPI gives typed
  request/response models and OpenAPI for free.
- **PostgreSQL with pgvector** as the single store for documents, chunks, embeddings, full-text
  search and, later, the graph tables. One database is simpler to run, back up and reason
  about than a separate vector database, and Postgres already has full-text search for the
  BM25 side of hybrid search.
- **psycopg 3 with a connection pool**, plain SQL, no ORM. Retrieval queries are SQL-heavy
  (vector operators, `ts_rank`, CTEs), and an ORM would mostly get in the way.
- **Angular 18** (standalone components, signals, OnPush) for the UI.
- **One origin through nginx:** nginx serves the Angular build and proxies `/api`. No CORS, and
  cookies stay simple when sign-in arrives.
- **Two health endpoints:** `/api/health` (liveness, never touches the database) and
  `/api/health/ready` (database answers and pgvector is enabled, otherwise 503). An
  orchestrator can restart a dead process without restarting it just because the database
  is slow.
- **Settings from environment variables** (`FILINGLENS_` prefix) via pydantic-settings.
- `create_app(settings)` is a factory, so tests build an app with exactly the settings they need.

Layout:

```
api/    FastAPI app (app/), tests (tests/), Dockerfile
web/    Angular app, nginx.conf, Dockerfile
docs/   ADRs
```

## Consequences

- The API image runs as a non-root user; the web image uses the unprivileged nginx image.
- The CSP keeps scripts to `'self'`. Styles need `'unsafe-inline'` because Angular adds
  component styles at runtime. Critical-CSS inlining is turned off, because it relies on an
  inline `onload` handler.
- CI runs three jobs: `api` (ruff and pytest against a real pgvector Postgres service), `web`
  (Karma in headless Chrome and a production build) and `compose` (the whole stack built
  with Docker Compose and checked through nginx).
