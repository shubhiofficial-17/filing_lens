from app.mcp.agent import McpAgentRag, action_validator, agent_messages, chunk_ids
from app.mcp.client import DirectToolbox
from app.mcp.tools import Tools
from tests.helpers import rag


def test_actions_are_validated_against_the_advertised_tools():
    validate = action_validator({"search_filings"})
    assert validate({"action": "answer", "extra": 1}) == {"action": "answer"}
    call = validate({"action": "call", "tool": "search_filings", "arguments": {"query": "x"}})
    assert call["tool"] == "search_filings"
    for bad in ({"action": "call", "tool": "rm_rf"}, {"action": "dance"},
                {"action": "call", "tool": "search_filings", "arguments": [1]}):
        try:
            validate(bad)
        except (ValueError, KeyError):
            continue
        raise AssertionError(f"accepted {bad}")


def test_direct_toolbox_mirrors_the_server_tools():
    box = DirectToolbox(Tools(rag()))
    names = {t["name"] for t in box.list_tools()}
    assert "search_filings" in names and "ask" not in names  # no recursion into ask
    assert "error" in box.call("search_filings", {"nope": 1})
    assert "error" in box.call("delete_everything", {})


def test_the_prompt_lists_tools_and_observations():
    messages = agent_messages("q?", [{"name": "t", "description": "d",
                                     "input_schema": {"properties": {"a": {}}}}],
                              [{"tool": "t", "arguments": {"a": 1}, "result": '{"x": 1}'}])
    assert messages[0]["content"].startswith("TASK: tool_agent")
    assert '- t: d args={"a": {}}' in messages[1]["content"]
    assert '1. t({"a": 1}) -> {"x": 1}' in messages[1]["content"]


def test_chunk_ids_come_from_search_results_and_graph_facts():
    assert chunk_ids({"results": [{"chunk_id": "a"}], "facts": [{"chunk_id": "b"}]}) == ["a", "b"]


def test_agent_chains_graph_lookup_then_search_and_cites_the_tool_results():
    answer = McpAgentRag(rag()).run(
        "Which company owns Helix Vision Ltd., and who was that company's CEO in fiscal 2025?"
    )
    steps = [s.name for s in answer.trace]
    assert steps[:4] == ["connect tools", "turn 1: decide", "turn 1: graph_lookup",
                         "turn 2: decide"]
    assert "turn 2: search_filings" in steps
    search = next(s for s in answer.trace if s.name == "turn 2: search_filings")
    assert search.data["arguments"]["tickers"] == ["NWRB"]
    assert "Maya Chen" in answer.text and answer.citations
    assert all(h.source == "mcp" for h in answer.retrieved)
