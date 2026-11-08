"""Toolboxes: how the MCP agent reaches its tools.

- `McpToolbox`: a real MCP client (the official SDK's `mcp.Client`) over stdio (it starts
  `python -m app.mcp.server` as a subprocess), streamable HTTP (a running server's URL), or
  in-process against an `MCPServer` object (tests).
- `DirectToolbox`: calls the same tool functions in-process, without a protocol. Used where
  the MCP package isn't installed and to keep the evaluation fast. The agent code is
  identical either way.

The MCP client is asynchronous and the pipelines are synchronous, so `McpToolbox` runs
one event loop on a background thread. A single long-lived task owns the `Client` context,
because the SDK's anyio task groups must be entered and exited in the same task. Calls are
submitted to that loop from any thread.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from typing import Protocol

from app.mcp.tools import AGENT_TOOLS, TOOL_SPECS, Tools

API_DIR = Path(__file__).resolve().parents[2]


class ToolboxError(Exception):
    pass


class Toolbox(Protocol):
    transport: str

    def list_tools(self) -> list[dict]: ...

    def call(self, name: str, arguments: dict) -> dict: ...

    def close(self) -> None: ...


class DirectToolbox:
    transport = "direct"

    def __init__(self, tools: Tools) -> None:
        self._tools = tools

    def list_tools(self) -> list[dict]:
        return [t for t in TOOL_SPECS if t["name"] in AGENT_TOOLS]

    def call(self, name: str, arguments: dict) -> dict:
        if name not in AGENT_TOOLS:
            return {"error": f"unknown tool {name}"}
        try:
            return getattr(self._tools, name)(**arguments)
        except TypeError as e:  # wrong or missing arguments
            return {"error": f"bad arguments for {name}: {e}"}

    def close(self) -> None:
        pass


class McpToolbox:
    def __init__(self, *, url: str | None = None, server=None, timeout: float = 60) -> None:
        self.transport = "mcp-http" if url else "mcp-memory" if server is not None else "mcp-stdio"
        self._url = url
        self._server = server
        self._timeout = timeout
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True,
                                        name="mcp-client")
        self._session = None
        self._closed: asyncio.Event | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._runner = None

    # --- lifecycle --------------------------------------------------------------------
    def start(self) -> McpToolbox:
        self._thread.start()
        self._runner = asyncio.run_coroutine_threadsafe(self._run(), self._loop)
        if not self._ready.wait(self._timeout):
            raise ToolboxError("the MCP server did not start in time")
        if self._error:
            raise ToolboxError(f"could not connect to the MCP server: {self._error}")
        return self

    async def _run(self) -> None:
        from mcp import Client

        self._closed = asyncio.Event()
        try:
            async with Client(self._target(), read_timeout_seconds=self._timeout) as client:
                self._session = client
                self._ready.set()
                await self._closed.wait()
        except BaseException as e:  # noqa: BLE001 - surfaced to the caller of start()
            self._error = e
            self._ready.set()

    def _target(self):
        if self._url:
            return self._url
        if self._server is not None:
            return self._server
        from mcp import StdioServerParameters

        env = {k: v for k, v in os.environ.items()
               if k.startswith(("FILINGLENS_", "PATH", "PYTHON", "HOME", "LANG"))}
        return StdioServerParameters(command=sys.executable, args=["-m", "app.mcp.server"],
                                     env=env, cwd=str(API_DIR))

    def close(self) -> None:
        if self._closed is not None:
            self._loop.call_soon_threadsafe(self._closed.set)
        if self._runner is not None:
            try:
                self._runner.result(timeout=10)
            except Exception:  # noqa: BLE001 - closing should never raise
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    # --- calls ------------------------------------------------------------------------
    def _submit(self, coro):
        if self._session is None:
            raise ToolboxError("the toolbox is not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self._timeout)

    def list_tools(self) -> list[dict]:
        listed = self._submit(self._session.list_tools())
        return [
            {"name": t.name, "description": (t.description or "").strip().split("\n")[0],
             "input_schema": t.input_schema}
            for t in listed.tools if t.name in AGENT_TOOLS
        ]

    def call(self, name: str, arguments: dict) -> dict:
        result = self._submit(self._session.call_tool(name, arguments))
        text = "".join(getattr(c, "text", "") for c in result.content)
        if result.is_error:
            return {"error": text or "tool error"}
        structured = result.structured_content
        if isinstance(structured, dict):
            # Newer SDKs wrap non-object return values as {"result": ...}.
            return structured.get("result", structured) if len(structured) == 1 else structured
        try:
            return json.loads(text)
        except ValueError:
            return {"text": text}


def open_toolbox(transport: str, tools: Tools, url: str | None = None) -> Toolbox:
    if transport == "direct":
        return DirectToolbox(tools)
    if transport == "http":
        if not url:
            raise ToolboxError("FILINGLENS_MCP_URL is required for the http transport")
        return McpToolbox(url=url).start()
    return McpToolbox().start()
