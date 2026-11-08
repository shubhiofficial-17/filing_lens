"""One set of store tests, run against every Store implementation."""

from app.fixtures.corpus import fixture_filings
from app.ingest.service import Ingestor
from app.models import Chunk, Filing, SearchFilter, Section
from app.rag.embeddings import HashingEmbedder


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


def _with_chunks(store):
    texts = {
        "A-2024:1#0": ("AAA", 2024, "Our chief executive officer is Jane Doe."),
        "A-2024:7#0": ("AAA", 2024, "Revenue was $10.0 million and HIPAA compliance costs rose."),
        "B-2024:7#0": ("BBB", 2024, "Revenue was $20.0 million in fiscal 2024."),
        "B-2025:7#0": ("BBB", 2025, "Revenue was $25.0 million in fiscal 2025."),
    }
    for fid in ("A-2024", "B-2024", "B-2025"):
        ticker, year = ("AAA", 2024) if fid == "A-2024" else ("BBB", int(fid[-4:]))
        items = sorted({cid.split(":")[1].split("#")[0] for cid in texts if cid.startswith(fid)})
        store.add_filing(_filing(fid, ticker, year),
                         [Section(f"{fid}:{i}", fid, i, "T", "x") for i in items])
    chunks = [Chunk(cid, cid.split("#")[0], cid.split(":")[0], t, y, cid.split(":")[1][0], text)
              for cid, (t, y, text) in texts.items()]
    embedder = HashingEmbedder()
    store.add_chunks(chunks, [c.text for c in chunks], embedder.embed([c.text for c in chunks]))
    return embedder


def check_vector_search_ranks_and_filters(store):
    embedder = _with_chunks(store)
    q = embedder.embed(["revenue in fiscal 2025"])[0]
    hits = store.vector_search(q, 2)
    assert hits[0].chunk.id == "B-2025:7#0"
    assert len(hits) == 2 and hits[0].score >= hits[1].score
    only_a = store.vector_search(q, 5, SearchFilter(tickers=("AAA",)))
    assert {h.chunk.ticker for h in only_a} == {"AAA"}
    assert store.count_chunks() == 4
    assert [c.id for c in store.get_chunks(["B-2024:7#0", "nope", "A-2024:1#0"])] == [
        "B-2024:7#0", "A-2024:1#0"]


def check_keyword_search_finds_exact_terms(store):
    _with_chunks(store)
    hits = store.keyword_search("HIPAA compliance", 3)
    assert hits and hits[0].chunk.id == "A-2024:7#0"
    years = store.keyword_search("revenue", 5, SearchFilter(years=(2025,)))
    assert [h.chunk.id for h in years] == ["B-2025:7#0"]
    assert store.keyword_search("the of and", 5) == []


def check_reingesting_a_filing_drops_its_chunks(store):
    _with_chunks(store)
    store.add_filing(_filing("B-2025", "BBB", 2025), [])
    assert store.count_chunks() == 3


def check_graph_is_replaced_per_filing(store):
    from app.models import Entity, Relation

    store.add_filing(_filing("A-2024", "AAA", 2024), [])
    store.add_filing(_filing("A-2025", "AAA", 2025), [])
    a = Entity("a", "A Inc.", "company")
    b, c = Entity("b", "B", "person"), Entity("c", "C", "person")
    store.add_graph("A-2024", [a, b], [Relation("a", "CEO", "b", "A-2024", 2024, "x")])
    store.add_graph("A-2025", [a, c], [Relation("a", "CEO", "c", "A-2025", 2025, "y")])
    assert [r.target_id for r in store.relations_for(["a"])] == ["b", "c"]
    store.add_graph("A-2025", [a, c], [])
    assert [r.target_id for r in store.relations_for(["c", "b"])] == ["b"]
    assert store.count_relations() == 1
    assert [e.id for e in store.list_entities()] == ["a", "b", "c"]


CHECKS = [
    check_add_and_read_back,
    check_adding_again_replaces,
    check_list_is_ordered_by_ticker_then_year,
    check_fixtures_ingest,
    check_vector_search_ranks_and_filters,
    check_keyword_search_finds_exact_terms,
    check_reingesting_a_filing_drops_its_chunks,
    check_graph_is_replaced_per_filing,
]
