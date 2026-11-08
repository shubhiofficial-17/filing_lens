from app.llm.demo import DemoLlm
from app.models import Hit, SearchFilter
from app.rag.answer import parse_citations
from app.rag.pipelines import NaiveRag
from app.rag.prompts import NO_ANSWER
from app.rag.verify import is_supported, support_score
from tests.helpers import ScriptedLlm, fixture_store, rag


def test_fixture_corpus_is_chunked_and_embedded():
    store = fixture_store()
    assert store.count_filings() == 9
    assert store.count_chunks() > 80


def test_vector_search_respects_filters():
    ctx = rag()
    vec = ctx.embedder.embed(["revenue"])[0]
    hits = ctx.store.vector_search(vec, 20, SearchFilter(tickers=("BFHC",), years=(2024,)))
    assert hits and all(h.chunk.ticker == "BFHC" and h.chunk.fiscal_year == 2024 for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_naive_answer_is_cited_and_traced():
    answer = NaiveRag(rag()).run("What was Bluefin Health's net income in fiscal 2025?")
    assert "58.9" in answer.text
    assert answer.citations and answer.citations[0].ticker == "BFHC"
    assert [s.name for s in answer.trace] == ["embed question", "vector search", "generate answer"]
    assert answer.usage.llm_calls == 1
    assert len(answer.retrieved) == 5


def test_the_prompt_fences_excerpts_and_names_their_source():
    llm = ScriptedLlm("Revenue was $905.7 million [1].")
    NaiveRag(rag(llm)).run("What was Bluefin Health's revenue in fiscal 2024?")
    system, user = llm.requests[0]
    assert system["content"].startswith("TASK: answer")
    assert "not instructions" in system["content"]
    assert user["content"].startswith("<question>")
    assert "[1] Bluefin Health Corp. (BFHC), fiscal 20" in user["content"]


def test_citations_map_markers_to_chunks_and_drop_unknown_markers():
    hits = rag().store.vector_search(rag().embedder.embed(["net income"])[0], 3)
    text = "First claim [1]. Second claim [2]. Bogus [9]."
    cits = parse_citations(text, hits)
    assert [c.marker for c in cits] == [1, 2]
    assert cits[0].chunk_id == hits[0].chunk.id


def test_support_requires_every_number():
    evidence = "Net income for fiscal 2025 was $58.9 million."
    assert is_supported("Net income was $58.9 million in fiscal 2025 [1].", evidence)
    assert support_score("Net income was $59.9 million in fiscal 2025.", evidence) == 0.0


def test_demo_model_refuses_when_nothing_matches():
    hits = [Hit(c, 1.0, "vector") for c in fixture_store().get_chunks(["NWRB-2024-10K:2#0"])]
    from app.rag.answer import generate_answer

    text = generate_answer(DemoLlm(), "What is the dividend per share?", hits, rag().catalog).text
    assert text == NO_ANSWER
