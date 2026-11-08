"""The real MCP server, through the MCP SDK (runs where the `mcp` package is installed)."""

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from app.mcp import server  # noqa: E402
from app.mcp.tools import Tools  # noqa: E402
from tests.helpers import rag  # noqa: E402


@pytest.fixture(autouse=True)
def fixture_tools(monkeypatch):
    monkeypatch.setattr(server, "tools", lambda: Tools(rag()))


def _payload(result) -> dict:
    """FastMCP.call_tool returns content blocks (older SDKs) or (content, structured)."""
    if isinstance(result, tuple):
        result = result[0]
    return json.loads(result[0].text)


def test_tools_are_listed_with_schemas():
    mcp = server.build_server()
    listed = asyncio.run(mcp.list_tools())
    names = {t.name for t in listed}
    assert {"list_companies", "search_filings", "get_section", "get_financials",
            "compare_companies", "graph_lookup", "ask"} <= names
    search = next(t for t in listed if t.name == "search_filings")
    assert "query" in search.inputSchema["properties"]


def test_calling_a_tool_through_the_server():
    mcp = server.build_server()
    result = asyncio.run(mcp.call_tool("get_financials", {"ticker": "SLEH", "fiscal_year": 2024}))
    assert _payload(result)["revenue"] == 1948.6


def test_resources_and_prompts_are_registered():
    mcp = server.build_server()
    templates = asyncio.run(mcp.list_resource_templates())
    assert any("filing/{ticker}" in t.uriTemplate for t in templates)
    prompts = asyncio.run(mcp.list_prompts())
    assert [p.name for p in prompts] == ["research_company"]
