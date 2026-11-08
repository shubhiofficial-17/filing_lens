"""One set of store tests, run against every Store implementation."""

from app.fixtures.corpus import fixture_filings
from app.ingest.service import Ingestor
from app.models import Filing, Section


def _filing(fid: str = "T-2024", ticker: str = "TST", year: int = 2024) -> Filing:
    return Filing(id=fid, ticker=ticker, company="Test Co", cik="1", fiscal_year=year)


def check_add_and_read_back(store):
    filing = _filing()
    sections = [
        Section(id="T-2024:1", filing_id="T-2024", item="1", title="Business", text="We sell."),
        Section(id="T-2024:7", filing_id="T-2024", item="7", title="MD&A", text="Revenue rose."),
    ]
    store.add_filing(filing, sections)

    assert store.get_filing("T-2024") == filing
    assert [s.item for s in store.list_sections("T-2024")] == ["1", "7"]
    assert store.get_section("T-2024:7").text == "Revenue rose."
    assert store.get_section("T-2024:9") is None
    assert store.get_filing("missing") is None


def check_adding_again_replaces(store):
    store.add_filing(_filing(), [Section("T-2024:1", "T-2024", "1", "B", "old")])
    store.add_filing(_filing(), [Section("T-2024:1", "T-2024", "1", "B", "new")])
    assert store.count_filings() == 1
    assert [s.text for s in store.list_sections("T-2024")] == ["new"]


def check_list_is_ordered_by_ticker_then_year(store):
    store.add_filing(_filing("B-2024", "BBB", 2024), [])
    store.add_filing(_filing("A-2025", "AAA", 2025), [])
    store.add_filing(_filing("A-2023", "AAA", 2023), [])
    assert [f.id for f in store.list_filings()] == ["A-2023", "A-2025", "B-2024"]


def check_fixtures_ingest(store):
    Ingestor(store).ingest_fixtures()
    assert store.count_filings() == len(fixture_filings())
    assert store.get_section("NWRB-2024-10K:1A") is not None


CHECKS = [
    check_add_and_read_back,
    check_adding_again_replaces,
    check_list_is_ordered_by_ticker_then_year,
    check_fixtures_ingest,
]
