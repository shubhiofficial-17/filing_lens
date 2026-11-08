from app.models import Chunk, Hit, SearchFilter
from app.rag.bm25 import Bm25Index
from app.rag.pipelines import HybridRag, NaiveRag
from app.rag.query import rewrite
from app.rag.retrieval import (
    LexicalReranker,
    coverage_groups,
    parse_grades,
    rrf,
    select_with_coverage,
)
from tests.helpers import rag


def _hit(cid: str, ticker: str = "AAA", year: int = 2024, text: str = "x") -> Hit:
    return Hit(Chunk(cid, cid, cid, ticker, year, "7", text), 1.0, "vector")


def test_bm25_prefers_rare_terms_and_shorter_documents():
    index = Bm25Index()
    index.add("a", "revenue revenue revenue grew")
    index.add("b", "revenue grew and HIPAA fines were paid")
    index.add("c", "HIPAA")
    scores = index.scores("HIPAA")
    assert max(scores, key=scores.get) == "c"
    assert "a" not in scores
    index.remove("c")
    assert set(index.scores("HIPAA")) == {"b"}


def test_rrf_rewards_agreement_between_rankings():
    a, b, c = _hit("a"), _hit("b"), _hit("c")
    fused = rrf([[a, b, c], [b, c]])
    assert [h.chunk.id for h in fused] == ["b", "c", "a"]
    assert fused[0].score == 1 / 62 + 1 / 61
    assert fused[0].source == "hybrid"


def test_glossary_rewrite_keeps_the_original_words():
    assert rewrite("Who is the CEO?") == "Who is the CEO? (chief executive officer)"
    assert rewrite("What was revenue?") == "What was revenue?"


def test_question_understanding_finds_companies_and_known_years():
    filt = rag().catalog.understand("Compare Northwind and Bluefin Health revenue, 2019 to 2024")
    assert set(filt.tickers) == {"NWRB", "BFHC"}
    assert filt.years == (2024,)


def test_coverage_selection_keeps_every_company_asked_about():
    hits = [_hit(f"a{i}", "AAA") for i in range(5)] + [_hit("b0", "BBB")]
    chosen = select_with_coverage(hits, 3, coverage_groups(SearchFilter(tickers=("AAA", "BBB"))))
    assert [h.chunk.id for h in chosen] == ["a0", "a1", "b0"]


def test_reranker_rewards_coverage_of_the_question():
    good = _hit("good", text="Research and development expense was $214.6 million.")
    bad = _hit("bad", text="Our headquarters are in Pittsburgh.")
    query = "research and development expense"
    ranked = LexicalReranker().rerank(query, [bad, good], rag().catalog)
    assert ranked[0].chunk.id == "good"


def test_llm_grades_are_parsed_defensively():
    assert parse_grades('```json\n{"grades": [{"passage": 2, "score": 9}]}\n```', 2) == [0.0, 9.0]
    assert parse_grades("no json here", 2) is None


def test_hybrid_answers_what_naive_misses():
    question = "Who was the CFO of Northwind Robotics in fiscal 2025?"
    assert "Laura Benson" not in NaiveRag(rag()).run(question).text
    answer = HybridRag(rag()).run(question)
    assert "Laura Benson" in answer.text
    names = [s.name for s in answer.trace]
    assert names == ["understand question", "hybrid search", "rerank", "generate answer"]
    assert answer.trace[0].data["tickers"] == ["NWRB"]


def test_hybrid_comparison_retrieves_both_companies():
    answer = HybridRag(rag()).run(
        "Compare the fiscal 2024 revenue of Bluefin Health and Solace Energy."
    )
    assert {h.chunk.ticker for h in answer.retrieved} >= {"BFHC", "SLEH"}
