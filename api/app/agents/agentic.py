"""Agentic RAG: plan the searches, check the evidence, search again, verify the answer.

    plan ──► for each step: gather (graph + hybrid) ─► sanitise ─► assess ─┐
              ▲                                         insufficient: rewrite, widen
              └─────────────────────────────────────────────────────────────┘
    merge evidence (round-robin across steps) ─► answer ─► verify citations

Every decision is a structured model call with a fallback, so a bad reply makes the
answer worse, never the request fail. Limits: 4 steps, 2 rounds per step, 10 excerpts.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.prompts import assess_messages, plan_messages
from app.agents.structured import complete_json
from app.agents.verify import verify_answer
from app.guardrails import sanitise_hits
from app.models import Answer, Hit, SearchFilter
from app.rag.answer import generate_answer
from app.rag.catalog import Catalog
from app.rag.pipelines import GraphRag, facts_as_notes, summarise_hits
from app.rag.trace import Trace

MAX_STEPS = 4
MAX_ROUNDS = 2
MAX_EXCERPTS = 10


@dataclass(frozen=True)
class Step:
    query: str
    tickers: tuple[str, ...] = ()
    years: tuple[int, ...] = ()
    uses_previous: bool = False


def plan_validator(catalog: Catalog):
    known_tickers = set(catalog.companies)
    known_years = {f.fiscal_year for f in catalog.filings.values()}

    def validate(data: dict) -> list[Step]:
        steps = []
        for raw in data["steps"][:MAX_STEPS]:
            query = str(raw["query"]).strip()[:300]
            if not query:
                continue
            steps.append(Step(
                query=query,
                tickers=tuple(t for t in (str(x).upper() for x in raw.get("tickers") or [])
                              if t in known_tickers),
                years=tuple(
                    y for y in (int(x) for x in raw.get("years") or []) if y in known_years
                ),
                uses_previous=bool(raw.get("uses_previous", False)),
            ))
        if not steps:
            raise ValueError("the plan has no steps")
        return steps

    return validate


def validate_assessment(data: dict) -> tuple[bool, str]:
    return bool(data["sufficient"]), str(data.get("query") or "").strip()[:300]


def round_robin(groups: list[list[Hit]], limit: int) -> list[Hit]:
    """Take the best hit of each group in turn, so every step keeps its evidence."""
    out: list[Hit] = []
    seen: set[str] = set()
    for i in range(max((len(g) for g in groups), default=0)):
        for g in groups:
            if i < len(g) and g[i].chunk.id not in seen:
                seen.add(g[i].chunk.id)
                out.append(g[i])
    return out[:limit]


class AgenticRag(GraphRag):
    name = "agentic"
    title = "Agentic RAG"
    description = (
        "Plans one search per company/year or per hop, checks whether the evidence is "
        "enough and searches again if not, strips instructions found in sources, and "
        "verifies every cited sentence before answering."
    )

    answer_model: str | None = None  # None = the default model

    def run(self, question: str, filt: SearchFilter | None = None) -> Answer:
        trace = Trace()
        text, evidence, _ = self.research_and_answer(question, filt, trace)
        return self.finish(question, text, evidence, trace)

    def research_and_answer(
        self, question: str, filt: SearchFilter | None, trace: Trace
    ) -> tuple[str, list[Hit], list]:
        """Plan, research every step, answer and verify. Returns (text, evidence, facts)."""
        steps = self.plan(question, filt, trace)

        groups: list[list[Hit]] = []
        facts: list = []
        previous: list[str] = []
        for i, step in enumerate(steps, 1):
            hits, step_facts, previous = self.research(i, step, filt, previous, trace)
            groups.append(hits)
            facts += [f for f in step_facts if f not in facts]

        with trace.step("merge evidence") as d:
            evidence = round_robin(groups, MAX_EXCERPTS)
            d["hits"] = summarise_hits(evidence)
        text = self.answer_and_verify(question, evidence, facts_as_notes(facts, evidence), trace)
        return text, evidence, facts

    def answer_and_verify(
        self, question: str, evidence: list[Hit], notes: str, trace: Trace
    ) -> str:
        with trace.step("generate answer", self.answer_model or "default model"):
            draft = trace.record(generate_answer(
                self.ctx.llm, question, evidence, self.ctx.catalog, notes=notes,
                model=self.answer_model,
            ))
        with trace.step("verify citations") as d:
            text, checks = verify_answer(draft.text, evidence)
            d["checks"] = [{"sentence": c.sentence, "status": c.status} for c in checks]
            d["removed"] = sum(c.status == "removed" for c in checks)
        return text

    def plan(self, question: str, filt: SearchFilter | None, trace: Trace) -> list[Step]:
        catalog = self.ctx.catalog
        inferred = catalog.understand(question)
        fallback = [Step(question, inferred.tickers or (), inferred.years or ())]
        with trace.step("plan") as d:
            steps, ok = complete_json(
                self.ctx.llm, plan_messages(question, catalog), plan_validator(catalog),
                fallback, trace,
            )
            if filt and (filt.tickers or filt.years):
                steps = [Step(s.query, s.tickers or filt.tickers or (), s.years or filt.years or (),
                              s.uses_previous) for s in steps]
            d.update(ok=ok, steps=[s.__dict__ for s in steps])
        return steps

    def research(
        self, i: int, step: Step, filt: SearchFilter | None, previous: list[str], trace: Trace
    ) -> tuple[list[Hit], list, list[str]]:
        tickers = step.tickers or (tuple(previous) if step.uses_previous else ())
        current = SearchFilter(tickers=tickers or None, years=step.years or None)
        query = step.query
        hits: list[Hit] = []
        found_facts: list = []
        bridges: list[str] = []
        for round_no in range(1, MAX_ROUNDS + 1):
            with trace.step(f"step {i}: search", f"round {round_no}") as d:
                d.update(query=query, tickers=list(current.tickers or []),
                         years=list(current.years or []))
            gathered = self.gather(query, current, trace)
            with trace.step(f"step {i}: sanitise sources") as d:
                hits, flags = sanitise_hits(gathered.hits)
                d["removed"] = [{"chunk": f.chunk_id, "sentence": f.sentence} for f in flags]
            found_facts, bridges = gathered.facts, gathered.bridges
            if round_no == MAX_ROUNDS:
                break
            with trace.step(f"step {i}: assess evidence") as d:
                (sufficient, better), ok = complete_json(
                    self.ctx.llm, assess_messages(query, hits, self.ctx.catalog),
                    validate_assessment, (True, ""), trace,
                )
                d.update(sufficient=sufficient, query=better, ok=ok)
            if sufficient:
                break
            # Search again: the suggested wording, and without the year filter.
            query = better or query
            current = SearchFilter(tickers=current.tickers)
        reached = bridges or list(dict.fromkeys(h.chunk.ticker for h in hits[:3]))
        return hits, found_facts, reached
