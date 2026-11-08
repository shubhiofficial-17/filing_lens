"""The MCP agent's client against the real server over stdio (a subprocess)."""

import pytest

pytest.importorskip("mcp")

from app.mcp.client import McpToolbox  # noqa: E402
from app.mcp.tools import AGENT_TOOLS  # noqa: E402


@pytest.fixture(scope="module")
def box():
    toolbox = McpToolbox(timeout=120).start()
    yield toolbox
    toolbox.close()


def test_lists_the_servers_tools(box):
    names = {t["name"] for t in box.list_tools()}
    assert names == AGENT_TOOLS
    assert box.transport == "mcp-stdio"


def test_calls_tools_and_decodes_results(box):
    data = box.call("get_financials", {"ticker": "NWRB", "fiscal_year": 2024})
    assert data["revenue"] == 1486.2
    results = box.call("search_filings", {"query": "ransomware", "tickers": ["BFHC"]})["results"]
    assert results[0]["chunk_id"].startswith("BFHC-")


def test_tool_errors_come_back_as_data(box):
    args = {"ticker": "NWRB", "fiscal_year": 1999, "item": "1"}
    assert "error" in box.call("get_section", args)
