# 0011. An agent that uses tools through MCP

Date: 2026-11-08
Status: accepted

## Context

Building an MCP server is half the protocol. The other half is the client: discovering
tools at run time, calling them, and handling their errors. The app's own agent should be
able to use FilingLens's tools exactly as Claude Desktop does.

## Decision

- **SDK v2.** The project uses the MCP Python SDK 2.x (`MCPServer` on the server side,
  `mcp.Client` on the client side). One `Client` class connects to a URL (streamable
  HTTP), a `StdioServerParameters` (subprocess) or an `MCPServer` object (in-process, used
  in tests).
- **`McpToolbox`** gives the synchronous pipelines a small facade: `list_tools()` and
  `call(name, args)`. The async client runs on a background event loop, and *one*
  long-lived task owns the `Client` context, because anyio task groups must be entered and
  exited in the same task. Tool errors (`is_error`) come back as `{"error": ...}` data, not
  exceptions.
- **`DirectToolbox`**: the same interface calling the same tool functions in-process. The
  evaluation uses it so runs stay fast and deterministic. A dedicated test runs the real
  stdio transport against a subprocess server.
- **The `mcp_agent` strategy** is ReAct with a JSON protocol. Each turn the model sees the
  tools as the server advertises them (name, description, input schema) plus the
  observations so far, and replies `{"action": "call", "tool": ..., "arguments": ...}` or
  `{"action": "answer"}`. Actions are validated against the advertised tool names. No
  provider-specific function calling is needed, so any chat model works through the
  gateway, and so does the demo model. Limits: 5 turns, 10 evidence chunks.
- **The answer is written from the chunks the tools returned.** Search results and graph
  facts carry `chunk_id`s. The final answer is generated from those chunks, after
  sanitising, and verified like every other strategy, so tool use doesn't weaken
  citations.
- `ask` is not offered to the agent, so it can't recurse into the full pipeline.
- One toolbox, meaning one MCP session or one subprocess, is opened per process and
  reused; the API closes it on shutdown. The transport is set with
  `FILINGLENS_MCP_TRANSPORT` (`stdio`, `http` with `FILINGLENS_MCP_URL`, or `direct`).

## Consequences

- In demo mode it scores close to the agentic strategies (about 93%) at about three calls
  per question. Here the model, not code, decides which tools to call, so a real model's
  quality matters more than for the fixed pipelines.
- A JSON-protocol agent spends a call per decision. Native function calling would save a
  little, at the cost of tying the agent to providers that support it.
