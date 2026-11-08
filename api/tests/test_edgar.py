import pytest

httpx = pytest.importorskip("httpx")

from app.ingest.edgar import EdgarClient, EdgarError  # noqa: E402
from app.ingest.service import Ingestor  # noqa: E402
from app.store.memory import InMemoryStore  # noqa: E402

SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-K", "10-K/A", "10-K"],
            "accessionNumber": ["a-1", "0000001-25-000010", "a-3", "0000001-24-000009"],
            "reportDate": ["2025-03-01", "2024-12-31", "2024-12-31", "2023-12-31"],
            "filingDate": ["2025-03-02", "2025-02-14", "2025-04-01", "2024-02-15"],
            "primaryDocument": ["x.htm", "abc-20241231.htm", "y.htm", "abc-20231231.htm"],
        }
    }
}
DOC = "<p>Item 1. Business</p><p>We sell widgets.</p><p>Item 7. MD&A</p><p>Sales grew.</p>"


def _client(seen: list[httpx.Request]) -> EdgarClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        url = str(request.url)
        if url.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"cik_str": 1234, "ticker": "ABC", "title": "Abc Inc"}})
        if "submissions/CIK0000001234.json" in url:
            return httpx.Response(200, json=SUBMISSIONS)
        if "/Archives/edgar/data/1234/" in url:
            return httpx.Response(200, text=DOC)
        return httpx.Response(404)

    return EdgarClient(
        "FilingLens test@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        min_interval=0,
    )


def test_lists_only_original_10ks_newest_first():
    found = _client([]).annual_reports("abc", limit=5)
    assert [f.filing.id for f in found] == ["0000001-25-000010", "0000001-24-000009"]
    first = found[0].filing
    assert (first.ticker, first.cik, first.fiscal_year) == ("ABC", "0000001234", 2024)
    assert found[0].document_url == (
        "https://www.sec.gov/Archives/edgar/data/1234/000000125000010/abc-20241231.htm"
    )


def test_sends_the_user_agent_on_every_request():
    seen: list = []
    _client(seen).annual_reports("ABC")
    assert seen and all(r.headers["User-Agent"] == "FilingLens test@example.com" for r in seen)


def test_requires_a_contact_user_agent():
    with pytest.raises(EdgarError):
        EdgarClient("FilingLens")


def test_unknown_ticker():
    with pytest.raises(EdgarError, match="unknown ticker"):
        _client([]).lookup("ZZZZ")


def test_ingest_from_edgar_end_to_end():
    store = InMemoryStore()
    results = Ingestor(store).ingest_edgar(_client([]), "ABC", limit=1)
    assert [r.sections for r in results] == [2]
    assert store.get_section("0000001-25-000010:7").text == "Sales grew."
