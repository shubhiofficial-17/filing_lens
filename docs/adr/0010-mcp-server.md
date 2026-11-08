# 0010. An MCP server for the filing tools

Date: 2026-11-08
Status: accepted

## Context

Search, financials and the knowledge graph are useful beyond this app's UI. An analyst
already working in Claude Desktop, VS Code or Cursor should be able to use them without
copying text around. The Model Context Protocol is the standard way to offer tools to any
MCP client.

## Decision

- **Tools are plain functions** (`app/mcp/tools.py`) over the same `RagContext` the API
  uses. The MCP server (`app/mcp/server.py`, built with the official Python SDK v2's
  `MCPServer`) is a thin wrapper around them. The tools are tested without MCP, and the server is tested
  through the SDK.
- **Tools**: `list_companies`, `search_filings`, `get_section`, `get_financials`,
  `compare_companies`, `graph_lookup` and `ask` (a full cited answer with a chosen
  strategy). Each validates and clamps its inputs, returns ids that can be cited
  (`chunk_id`, `section_id`), and returns `{"error": ...}` instead of raising, with hints
  such as `available_items`, so a model can recover.
- **Resources**: `filinglens://companies` and
  `filinglens://filing/{ticker}/{fiscal_year}/{item}`, for clients that browse resources.
  **Prompt**: `research_company`, a starting brief.
- **Two transports**: stdio for desktop clients (logs go to stderr, because stdout is the
  protocol channel), and streamable HTTP at `/mcp` for remote clients. In Docker Compose
  that runs as its own `mcp` service, published on localhost only.
- **Server instructions** tell the client model to treat tool output as quoted data, not
  instructions. That is the same rule as the app's own prompts.
- The server reads the same `FILINGLENS_*` settings as the API, so it can share the
  Postgres database or load the fixture corpus in memory.

## Consequences

- One implementation of search and lookup serves the web app, the evaluation, the MCP
  server and (next milestone) the app's own MCP agent.
- The HTTP transport has no authentication, which is why Compose binds it to 127.0.0.1.
  Exposing it beyond localhost needs a token check or an authenticating proxy in front
  ([docs/deploy.md](../deploy.md)).
- `ask` runs the full pipeline, model calls included, so it costs what an API question
  costs. The other tools never call a model.
