"""The real MCP server, through the MCP SDK."""

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from app.mcp import server  # noqa: E402
from app.mcp.client import McpToolbox  # noqa: E402
from app.mcp.tools import AGENT_TOOLS, Tools  # noqa: E402
from tests.helpers import rag  # noqa: E402


@pytest.fixture(autouse=True)
def fixture_tools(monkeypatch):
    monkeypatch.setattr(server, "tools", lambda: Tools(rag()))


def test_tools_are_listed_with_schemas():
    listed = asyncio.run(server.build_server().list_tools())
    names = {t.name for t in listed}
    assert AGENT_TOOLS | {"ask"} == names
    search = next(t for t in listed if t.name == "search_filings")
    assert search.input_schema["required"] == ["query"]


def test_calling_a_tool_on_the_server():
    args = {"ticker": "SLEH", "fiscal_year": 2024}
    result = asyncio.run(server.build_server().call_tool("get_financials", args))
    assert not result.is_error
    assert json.loads(result.content[0].text)["revenue"] == 1948.6


def test_resources_and_prompts_are_registered():
    mcp = server.build_server()
    templates = asyncio.run(mcp.list_resource_templates())
    uris = [t.uri_template for t in templates]
    assert uris == ["filinglens://filing/{ticker}/{fiscal_year}/{item}"]
    assert [p.name for p in asyncio.run(mcp.list_prompts())] == ["research_company"]


def test_a_client_session_in_process():
    box = McpToolbox(server=server.build_server()).start()
    try:
        assert {t["name"] for t in box.list_tools()} == AGENT_TOOLS
        data = box.call("get_financials", {"ticker": "NWRB", "fiscal_year": 2024})
        assert data["revenue"] == 1486.2
        assert box.call("no_such_tool", {})["error"]
    finally:
        box.close()
