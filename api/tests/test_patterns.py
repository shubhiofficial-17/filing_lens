from app.agents.patterns import RoutedRag, Router, calculate_change, validate_critique
from app.llm.demo import DemoLlm
from app.models import Chunk, Hit
from app.rag.trace import Trace
from tests.helpers import rag


class RecordingLlm(DemoLlm):
    """The demo model, recording which model name each call asked for."""

    def __init__(self) -> None:
        self.models: list[str | None] = []

    def complete(self, messages, *, model=None, max_tokens=700, json_mode=False):
        self.models.append(model)
        return super().complete(messages, model=model, max_tokens=max_tokens, json_mode=json_mode)


def test_router_rules():
    router = Router(rag())
    route = lambda q: router.route(q, Trace()).route  # noqa: E731
    assert route("What was Bluefin Health's revenue in fiscal 2024?") == "simple"
    assert route("Compare Northwind Robotics and Solace Energy revenue.") == "complex"
    assert route("How did revenue change from fiscal 2023 to fiscal 2025?") == "complex"
    assert route("Which company owns Helix Vision Ltd.?") == "complex"


def test_long_unclear_questions_are_classified_by_the_model():
    q = ("Thinking about everything the filing says regarding the people who run the business "
         "day to day and the way they describe their roles, who is in charge at Bluefin Health?")
    trace = Trace()
    route = Router(rag()).route(q, trace)
    assert route.decided_by == "model" and trace.usage.llm_calls == 1


def _hit(year: int) -> Hit:
    return Hit(Chunk(f"c{year}", "s", "f", "ABC", year, "7", "x"), 1.0, "hybrid")


def test_calculator_uses_cited_numbers_for_the_years_asked():
    text = ("Revenue for fiscal 2023 was $100.0 million [1]. "
            "Revenue for fiscal 2025 was $150.5 million [2].")
    out = calculate_change("How did revenue change from 2023 to 2025?", text,
                           [_hit(2023), _hit(2025)])
    assert out == ("Calculated: from $100.0 million in fiscal 2023 to $150.5 million in fiscal "
                   "2025 is an increase of 50.5% (inputs [1] and [2]).")


def test_calculator_stays_quiet_without_two_clear_values():
    assert calculate_change("What was revenue in 2024?", "x [1].", [_hit(2024)]) is None
    text = "Revenue for fiscal 2023 was $100.0 million [1]."
    assert calculate_change("How did it change from 2023 to 2025?", text, [_hit(2023)]) is None


def test_critique_output_is_validated():
    validate = validate_critique(rag().catalog)
    got = validate({"missing": [{"ticker": "sleh", "year": 2024}, {"ticker": "NOPE"}]})
    assert got == [("SLEH", 2024)]


def test_simple_questions_cost_one_model_call():
    answer = RoutedRag(rag()).run("What was Bluefin Health's net income in fiscal 2025?")
    assert "58.9" in answer.text
    assert answer.usage.llm_calls == 1
    assert answer.trace[0].data["route"] == "simple"


def test_complex_questions_use_the_strong_model_for_the_answer_and_get_a_calculation():
    llm = RecordingLlm()
    ctx = rag(llm)
    ctx.strong_model = "big-model"
    answer = RoutedRag(ctx).run(
        "How did Northwind Robotics' revenue change between fiscal 2023 and fiscal 2025?"
    )
    assert "Calculated:" in answer.text and "37.3%" in answer.text
    assert llm.models.count("big-model") == 1  # only the final answer
    assert [s.name for s in answer.trace][-2:] == ["reflect: critique", "calculator"]
