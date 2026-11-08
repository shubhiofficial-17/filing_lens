"""Three more GenAI patterns, combined in the `routed` strategy:

- **Router**: send each question to the cheapest strategy (and model) that can answer it.
  Simple lookups go to one-call hybrid/graph retrieval; comparisons, trends and multi-hop
  questions go to the agent, with the strong model for the final answer.
- **Reflection**: after the agent drafts an answer, a critic checks it against the
  question. Is every company and year asked about covered by a citation? Missing coverage
  triggers a targeted search and a revised answer.
- **Calculator tool**: models are unreliable at arithmetic, so a change between two
  reported numbers is computed in code and appended as a labelled calculation, with its
  inputs cited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.agentic import AgenticRag
from app.agents.structured import complete_json
from app.graph.retrieve import wanted_relations
from app.guardrails import sanitise_hits
from app.models import Answer, Hit, SearchFilter
from app.rag.catalog import Catalog
from app.rag.pipelines import GraphRag, HybridRag, facts_as_notes, summarise_hits
from app.rag.prompts import DATA_RULE, NO_ANSWER, excerpts
from app.rag.trace import Trace
from app.text import sentences, years_in

COMPLEX_WORDS = re.compile(
    r"\b(compare|compared|comparison|change|changed|trend|versus|vs\.?|differ|difference|why|"
    r"between|higher|lower|both|each|that company|which company|the company that|"
    r"the company whose|and who|and what|and how)\b",
    re.I,
)

ROUTE_SYSTEM = """TASK: route
Classify the question about SEC filings.
"simple": one fact about one company and one year.
"complex": comparisons, changes over time, explanations (why), or facts that depend on
another fact (multi-hop).
Reply with JSON only: {"route": "simple"}"""

CRITIQUE_SYSTEM = f"""TASK: critique
Check the draft answer against the question and the excerpts.
List each company (ticker) and fiscal year the question asks about that no cited excerpt
covers. Reply with JSON only:
{{"missing": [{{"ticker": "ABC", "year": 2024}}], "issues": ["..."]}}
{DATA_RULE}"""


@dataclass(frozen=True)
class Route:
    route: str  # "simple" | "complex"
    reason: str
    decided_by: str  # "rules" | "model"


class Router:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    def route(self, question: str, trace: Trace) -> Route:
        catalog: Catalog = self.ctx.catalog
        tickers = catalog.mentioned_tickers(question)
        years = set(years_in(question))
        if len(tickers) > 1:
            return Route("complex", f"{len(tickers)} companies", "rules")
        if len(years) > 1:
            return Route("complex", f"{len(years)} years", "rules")
        if m := COMPLEX_WORDS.search(question):
            return Route("complex", f"'{m.group(0)}'", "rules")
        if len(question.split()) <= 25:
            return Route("simple", "one company, one year, a direct question", "rules")
        # Long questions without clear signals: let the model decide.
        messages = [{"role": "system", "content": ROUTE_SYSTEM},
                    {"role": "user", "content": f"<question>{question}</question>"}]
        route, ok = complete_json(self.ctx.llm, messages, _validate_route, "complex", trace)
        return Route(route, "model classification" if ok else "fallback", "model")


def _validate_route(data: dict) -> str:
    if data["route"] not in ("simple", "complex"):
        raise ValueError(f"unknown route {data['route']!r}")
    return data["route"]


def critique_messages(
    question: str, draft: str, hits: list[Hit], catalog: Catalog
) -> list[dict[str, str]]:
    user = (f"<question>{question}</question>\n<draft>{draft}</draft>\n"
            f"<excerpts>\n{excerpts(hits, catalog)}\n</excerpts>\n"
            f"<companies>{', '.join(f'{n} ({t})' for t, n in catalog.companies.items())}"
            "</companies>")
    return [{"role": "system", "content": CRITIQUE_SYSTEM}, {"role": "user", "content": user}]


def validate_critique(catalog: Catalog):
    def validate(data: dict) -> list[tuple[str, int | None]]:
        out = []
        for m in data.get("missing", [])[:4]:
            ticker = str(m["ticker"]).upper()
            year = int(m["year"]) if m.get("year") else None
            if ticker in catalog.companies:
                out.append((ticker, year))
        return out
    return validate


_MONEY_RE = re.compile(r"\$?(\d{1,3}(?:,\d{3})*\.\d) million")
_MARK_RE = re.compile(r"\[(\d+)\]")


def calculate_change(question: str, text: str, hits: list[Hit]) -> str | None:
    """'How did X change from 2023 to 2025?' -> 'Calculated: an increase of 37.3% ...'.

    Uses only numbers stated in cited sentences, matched to years by the excerpt each
    sentence cites. Returns None unless exactly two years have exactly one value each."""
    if not re.search(r"\bchange|changed|grow|grew|increase|decrease|decline\b", question, re.I):
        return None
    years = sorted(set(years_in(question)))
    if len(years) != 2:
        return None
    values: dict[int, tuple[float, int]] = {}
    for s in sentences(text):
        marks = [int(m) for m in _MARK_RE.findall(s)]
        nums = _MONEY_RE.findall(s)
        if len(marks) != 1 or not 1 <= marks[0] <= len(hits) or not nums:
            continue
        year = hits[marks[0] - 1].chunk.fiscal_year
        sentence_years = years_in(s)
        if sentence_years:
            year = sentence_years[0]
        if year in years and year not in values:
            values[year] = (float(nums[0].replace(",", "")), marks[0])
    if set(values) != set(years):
        return None
    (old, m1), (new, m2) = values[years[0]], values[years[1]]
    if old == 0:
        return None
    pct = (new - old) / abs(old) * 100
    word = "an increase" if new >= old else "a decrease"
    return (f"Calculated: from ${old:,.1f} million in fiscal {years[0]} to ${new:,.1f} million "
            f"in fiscal {years[1]} is {word} of {abs(pct):.1f}% (inputs [{m1}] and [{m2}]).")


class RoutedRag(AgenticRag):
    name = "routed"
    title = "Router + reflection"
    description = (
        "A router sends simple lookups to one-call hybrid or graph retrieval and hard "
        "questions to the agent with the strong model; a critic checks coverage and "
        "triggers targeted searches; a calculator tool computes changes."
    )

    def run(self, question: str, filt: SearchFilter | None = None) -> Answer:
        trace = Trace()
        with trace.step("route") as d:
            route = Router(self.ctx).route(question, trace)
            d.update(route=route.route, reason=route.reason, decided_by=route.decided_by)

        if route.route == "simple":
            return self.simple(question, filt, trace)

        self.answer_model = self.ctx.strong_model
        text, evidence, facts = self.research_and_answer(question, filt, trace)
        text, evidence = self.reflect(question, text, evidence, facts, trace)
        with trace.step("calculator") as d:
            calc = calculate_change(question, text, evidence) if text != NO_ANSWER else None
            d["result"] = calc or "nothing to calculate"
        if calc:
            text = f"{text} {calc}"
        return self.finish(question, text, evidence, trace)

    def simple(self, question: str, filt: SearchFilter | None, trace: Trace) -> Answer:
        """One retrieval pass, one model call: graph-aware if the question is relational."""
        if wanted_relations(question) or self.ctx.graph.mentions(question):
            found = GraphRag.gather(self, question, filt, trace)
            hits, notes = found.hits, facts_as_notes(found.facts, found.hits)
        else:
            hits, notes = HybridRag.retrieve(self, question, filt, trace), ""
        with trace.step("sanitise sources") as d:
            hits, flags = sanitise_hits(hits)
            d["removed"] = [{"chunk": f.chunk_id, "sentence": f.sentence} for f in flags]
        text = self.answer_and_verify(question, hits, notes, trace)
        return self.finish(question, text, hits, trace)

    def reflect(
        self, question: str, text: str, evidence: list[Hit], facts: list, trace: Trace
    ) -> tuple[str, list[Hit]]:
        catalog = self.ctx.catalog
        with trace.step("reflect: critique") as d:
            missing, ok = complete_json(
                self.ctx.llm, critique_messages(question, text, evidence, catalog),
                validate_critique(catalog), [], trace,
            )
            d.update(missing=[f"{t} {y or ''}".strip() for t, y in missing], ok=ok)
        if not missing:
            return text, evidence

        extra: list[Hit] = []
        for ticker, year in missing:
            with trace.step("reflect: targeted search", f"{ticker} {year or ''}".strip()) as d:
                filt = SearchFilter(tickers=(ticker,), years=(year,) if year else None)
                hits = HybridRag.retrieve(self, question, filt, Trace())[:3]
                extra += [h for h in hits if h.chunk.id not in {e.chunk.id for e in evidence}]
                d["hits"] = summarise_hits(hits)
        if not extra:
            return text, evidence
        # The new evidence goes first, so the revised answer is built around it.
        revised = extra + evidence
        return self.answer_and_verify(question, revised, facts_as_notes(facts, revised),
                                      trace), revised
