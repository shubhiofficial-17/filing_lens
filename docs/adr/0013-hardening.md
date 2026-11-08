# 0013. Hardening, end-to-end tests and deployment

Date: 2026-11-08
Status: accepted

## Context

Every `/api/ask` costs model calls, ingestion downloads from a third party, and the MCP
server hands tools to any client that connects. The pieces are tested on their own; the
whole stack also has to work together behind nginx.

## Decision

- **Rate limits**: per-client-IP token buckets. `/api/ask` allows 30 requests per minute
  and ingestion 5, both configurable, with `0` turning a limit off. Limited requests get a
  429 with `Retry-After`. Buckets live in memory and idle clients are evicted. The LLM
  Gateway's team budgets are the hard cap on spend, and this limit stops one client from
  using all of it.
- **Client IPs**: uvicorn trusts `X-Forwarded-For` (`--forwarded-allow-ips *`) because
  the API is only reachable through nginx. The Dockerfile says so next to the setting.
- **Input limits**: questions are 3–500 characters, at most 10 tickers and 10 years per
  request, and nginx caps request bodies at 1 MB. Tools clamp their own inputs.
- **Request log**: one line per request with method, path, status and time, plus `nosniff`
  on API responses. The CSP and security headers are set in nginx.
- **Startup race**: the API and the MCP server can start together against an empty
  database. Seeding the fixtures happens under a Postgres advisory lock (and schema
  creation under another), so only one of them ingests.
- **End-to-end tests** (Playwright, in CI against `docker compose up`):
  1. asking a question shows a cited answer, its source and its trace
  2. comparing all seven strategies on the injection question: the agent drops the planted
     instruction, and naive RAG repeats it
  3. the evaluation page shows the report
  4. browsing a filing's sections

  Before Playwright, CI also sends a raw `initialize` request to the MCP server over
  streamable HTTP.
- **Deployment guide** (`docs/deploy.md`): services and ports, TLS, the model gateway,
  embeddings, EDGAR, securing the MCP endpoint, scaling and a go-live checklist.

## Consequences

- Rate limits are per process. Several instances need a shared store (Redis) for one
  global limit.
- The MCP HTTP endpoint has no authentication of its own, so it is published on localhost
  only. Exposing it needs a token-checking proxy.
