from app.mcp.tools import Tools, parse_statement
from tests.helpers import rag


def tools() -> Tools:
    return Tools(rag())


def test_list_companies_shows_every_filing():
    companies = tools().list_companies()["companies"]
    assert [c["ticker"] for c in companies] == ["BFHC", "NWRB", "SLEH"]
    assert [f["fiscal_year"] for f in companies[0]["filings"]] == [2023, 2024, 2025]


def test_search_returns_citable_chunks_and_clamps_k():
    results = tools().search_filings("ransomware attack", ["bfhc"], [2024], k=50)["results"]
    assert 1 <= len(results) <= 10
    assert results[0]["chunk_id"].startswith("BFHC-2024-10K:")
    assert tools().search_filings("   ") == {"error": "query is empty"}


def test_financials_are_read_from_the_income_statement():
    data = tools().get_financials("BFHC", 2023)
    assert data["revenue"] == 812.3 and data["net_income"] == -45.2
    assert data["source"] == "BFHC-2023-10K:8"
    assert "error" in tools().get_financials("BFHC", 2019)


def test_compare_companies_ranks_the_metric():
    data = tools().compare_companies(["NWRB", "BFHC"], 2025, "research and development")
    assert data["metric"] == "research_and_development"
    assert data["highest"] == "NWRB"
    assert [r["value"] for r in data["rows"]] == [251.3, 131.0]


def test_get_section_lists_items_when_missing():
    assert tools().get_section("NWRB", 2024, "1a")["section_id"] == "NWRB-2024-10K:1A"
    missing = tools().get_section("NWRB", 2024, "9")
    assert missing["available_items"] == ["1", "1A", "2", "3", "7", "8"]


def test_graph_lookup_and_ask():
    graph = tools().graph_lookup("Who owns SunSpan Brasil?")
    assert graph["companies"] == ["SLEH"] and graph["facts"][0]["relation"] == "OWNS"
    answer = tools().ask("What was Bluefin Health's net income in fiscal 2025?", "hybrid")
    assert "58.9" in answer["answer"] and answer["citations"]
    assert "error" in tools().ask("x", "nope")


def test_statement_parser_handles_losses_and_missing_columns():
    table = "| (in millions) | Fiscal 2024 | Fiscal 2023 |\n| Revenue | 1,200.5 | 900.0 |\n" \
            "| Net income (loss) | (3.5) | 2.0 |"
    assert parse_statement(table, 2024) == {"revenue": 1200.5, "net_income": -3.5}
    assert parse_statement(table, 2019) == {}
