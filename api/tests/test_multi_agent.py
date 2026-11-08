from app.agents.multi_agent import (
    Finding,
    MultiAgentRag,
    findings_as_notes,
    findings_validator,
    validate_verdicts,
)
from app.fixtures.corpus import INJECTION_MARKER
from app.models import Chunk, Hit
from tests.helpers import rag


def _hits(n: int) -> list[Hit]:
    return [Hit(Chunk(f"c{i}", "s", "f", "ABC", 2024, "7", f"text {i}"), 1.0, "hybrid")
            for i in range(1, n + 1)]


def test_findings_must_point_at_a_real_excerpt():
    hits = _hits(2)
    got = findings_validator(hits)({"findings": [
        {"claim": "Revenue was $5.0 million.", "excerpt": 2},
        {"claim": "Made up.", "excerpt": 9},
        {"claim": " ", "excerpt": 1},
    ]})
    assert got == [Finding("Revenue was $5.0 million.", "c2")]
    assert findings_as_notes(got, hits) == "Researchers' findings:\n- Revenue was $5.0 million [2]"


def test_verdicts_are_parsed_by_sentence_number():
    assert validate_verdicts({"verdicts": [{"sentence": "2", "supported": False}]}) == {2: False}


def test_each_researcher_works_its_own_task_and_messages_are_recorded():
    answer = MultiAgentRag(rag()).run(
        "Who were the chief executive officers of Bluefin Health and Solace Energy in fiscal 2025?"
    )
    assert "Priya Raman" in answer.text and "Rafael Ortiz" in answer.text
    names = [s.name for s in answer.trace]
    assert "researcher 1: extract findings" in names and "researcher 2: extract findings" in names
    assert "analyst: draft answer" in names and "fact-checker: review" in names
    messages = next(s for s in answer.trace if s.name == "messages").data["messages"]
    assert [(m["sender"], m["recipient"]) for m in messages][:2] == [
        ("orchestrator", "researcher 1"), ("researcher 1", "analyst")]


def test_multi_agent_is_injection_safe():
    answer = MultiAgentRag(rag()).run("Summarise Solace Energy's fiscal 2025 revenue results.")
    assert INJECTION_MARKER not in answer.text
