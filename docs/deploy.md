# Deploying FilingLens

## What runs

| Service | Image | Port | Notes |
|---|---|---|---|
| `web` | nginx + the Angular build | 8080 | the only public entry point; serves the app and proxies `/api` |
| `api` | Python (FastAPI) | 8000, internal | trusts `X-Forwarded-For` from nginx (rate limits are per client IP) |
| `mcp` | the same Python image | 8001, localhost | MCP tools over streamable HTTP at `/mcp` |
| `db` | `pgvector/pgvector:pg16` | 5432, internal | documents, chunks, vectors, full-text index, graph |

## Single server

```bash
cp .env.example .env      # set the model endpoint, EDGAR user agent, limits
docker compose up --build -d
```

Put a TLS-terminating proxy in front of port 8080, for example Caddy:

```
filinglens.example.com {
    reverse_proxy localhost:8080
}
```

## Models

FilingLens talks to any OpenAI-compatible endpoint. The intended setup is the
[LLM Gateway](https://github.com/shubhiofficial-17/llm_gateway), which holds the provider
keys, falls back between providers, caches and enforces per-team budgets:

```
FILINGLENS_LLM_BASE_URL=http://gateway:8080/v1
FILINGLENS_LLM_API_KEY=<a gateway team key>
FILINGLENS_LLM_MODEL=gpt-4o-mini
FILINGLENS_LLM_STRONG_MODEL=claude-sonnet-4-5
```

With nothing set, the demo model (deterministic, not an AI) is used. Everything works, and
answers are extractive.

Embeddings: set `FILINGLENS_EMBEDDINGS_BASE_URL` and `FILINGLENS_EMBEDDING_DIM`. The vector
column's size is fixed when the database is created, so changing the dimension needs a fresh
database (`docker compose down -v`) and re-ingestion.

## Real filings

Set `FILINGLENS_EDGAR_USER_AGENT="FilingLens you@example.com"` (SEC requires contact
details), then ingest from the Filings page or:

```bash
curl -X POST http://localhost:8080/api/filings/ingest \
  -H 'Content-Type: application/json' -d '{"ticker": "MSFT", "limit": 3}'
```

For real filings, consider `LlmExtractor` for the knowledge graph. The rule-based extractor
only knows the phrasings in the fixture corpus.

## The MCP server

- **Local desktop clients (stdio)**: see the README's "Use it from Claude Desktop" section.
- **Remote clients (HTTP)**: the `mcp` service is published on `127.0.0.1:8001` only. It has
  no authentication, so to expose it, put it behind a proxy that checks a token, for example
  nginx with `if ($http_authorization != "Bearer <token>") { return 401; }`, and serve it
  over HTTPS.

## Scaling out

- **API instances** are stateless except for two things: rate-limit buckets, which are
  per process (move them to Redis for a shared limit), and the MCP agent's stdio
  subprocess, which is per process.
- **Postgres**: HNSW (vectors) and GIN (full text) indexes are created automatically. For
  large corpora, raise `hnsw.ef_search` for better recall under filters, or partition
  `chunks` by ticker.
- **Ingestion** takes an advisory lock while seeding, so instances starting together don't
  ingest twice. EDGAR ingestion is synchronous in the request; for bulk loads, run it as a
  job (`python -c "..."` with the `Ingestor`) instead of through the API.

## Go-live checklist

- [ ] `FILINGLENS_LLM_BASE_URL` points at the gateway, and the gateway has a budget for this team
- [ ] Postgres password changed from the compose default, and backups configured
- [ ] TLS in front of `web`; port 8000 not published
- [ ] `FILINGLENS_RATE_LIMIT_ASK` set for expected traffic
- [ ] MCP HTTP either kept on localhost or behind authentication
- [ ] `python -m app.eval.run` run against the real model, and the report committed
