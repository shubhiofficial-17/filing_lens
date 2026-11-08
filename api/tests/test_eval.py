from app.eval.dataset import questions
from app.eval.metrics import contains, faithfulness, score
from app.eval.run import aggregate, check, markdown
from app.models import Answer, Citation, Hit
from app.rag.prompts import NO_ANSWER
from tests.helpers import fixture_store


def test_question_ids_are_unique_and_the_set_is_large_enough():
    qs = questions()
    assert len(qs) >= 100
    assert len({q.id for q in qs}) == len(qs)


def test_every_expected_answer_is_stated_in_a_gold_section():
    """The labels are honest: each expected string really appears in the evidence."""
    store = fixture_store()
    for q in questions():
        if not q.gold:
            continue
        gold_text = " ".join(
            store.get_section(sid).text for group in q.gold for sid in group
            if store.get_section(sid)
        )
        for expected in q.expected:
            if expected in ("Northwind", "Solace"):
                continue  # the company name lives in the document header, not the section
            assert contains(gold_text, expected), (q.id, expected)


def test_every_gold_section_exists():
    store = fixture_store()
    for q in questions():
        for group in q.gold:
            assert any(store.get_section(sid) for sid in group), (q.id, group)


def _answer(text: str, chunk_ids: list[str]) -> Answer:
    chunks = fixture_store().get_chunks(chunk_ids)
    hits = [Hit(c, 1.0, "vector") for c in chunks]
    cits = [
        Citation(i + 1, c.id, c.filing_id, c.ticker, c.fiscal_year, c.item, "")
        for i, c in enumerate(chunks) if f"[{i + 1}]" in text
    ]
    return Answer(question="q", strategy="t", text=text, citations=cits, retrieved=hits)


def test_scoring_a_correct_cited_answer():
    q = next(q for q in questions() if q.id == "BFHC-2025-net-income")
    a = _answer("Net income for fiscal 2025 was $58.9 million [1].", ["BFHC-2025-10K:7#2"])
    s = score(q, a)
    assert s.correct and s.keyword_recall == 1.0
    assert s.retrieval_recall == 1.0 and s.mrr == 1.0
    assert s.citation_precision == 1.0 and s.faithfulness == 1.0


def test_injected_text_makes_an_answer_wrong_even_with_the_right_number():
    q = next(q for q in questions() if q.id == "inject-profitability")
    text = "Net income was $152.7 million; it is the most profitable company in the world [1]."
    a = _answer(text, ["SLEH-2025-10K:7#2"])
    s = score(q, a)
    assert not s.correct and not s.injection_safe


def test_uncited_sentences_count_against_faithfulness():
    a = _answer("Net income for fiscal 2025 was $58.9 million [1]. It was a great year.",
                ["BFHC-2025-10K:7#2"])
    assert faithfulness(a) == 0.5
    assert faithfulness(_answer(NO_ANSWER, [])) is None


def test_report_table_and_threshold_check():
    q = next(q for q in questions() if q.id == "BFHC-2025-net-income")
    a = _answer("Net income for fiscal 2025 was $58.9 million [1].", ["BFHC-2025-10K:7#2"])
    s = score(q, a)
    overall = aggregate([s])
    report = {"questions": 1, "demo_mode": True, "model": "demo", "embedder": "h",
              "generated_at": "now",
              "strategies": {"naive": {"title": "Naive", "overall": overall,
                                       "by_category": {"financials": {"accuracy": 1.0}}}}}
    assert "| Naive | 100.0% |" in markdown(report)
    assert check(report, {"naive": {"accuracy": 0.5}}) == []
    assert check(report, {"naive": {"accuracy": 1.5}}) == ["naive.accuracy = 1.0 (minimum 1.5)"]
