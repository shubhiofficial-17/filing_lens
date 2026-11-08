"""Multi-agent research: researchers, an analyst and a fact-checker.

    orchestrator ── plan ──► researcher 1..n   (one per research task, own evidence)
                                 │ findings: short claims, each tied to an excerpt
                                 ▼
                             analyst          (writes the answer from the findings)
                                 │ draft
                                 ▼
                             fact-checker     (model verdicts + the deterministic check)
                                 │ unsupported sentences?  ── once ──► analyst revises
                                 ▼
                             final answer

Each agent has one job and a narrow prompt. Agents talk only through messages, which are
recorded in the trace, so you can read exactly what each one was told and what it said.
Researchers never see each other's evidence; the analyst never searches; the fact-checker
never writes. Separating "find", "write" and "check" is the point. A model is a much
better critic of a claim it didn't write.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.agentic import MAX_EXCERPTS, AgenticRag, round_robin
from app.agents.structured import complete_json
from app.agents.verify import verify_answer
from app.models import Answer, Hit, SearchFilter
from app.rag.answer import generate_answer
from app.rag.catalog import Catalog
from app.rag.pipelines import facts_as_notes, summarise_hits
from app.rag.prompts import DATA_RULE, NO_ANSWER, excerpts
from app.rag.trace import Trace
from app.text import sentences

RESEARCH_SYSTEM = f"""TASK: research
You are a researcher. From the excerpts, extract the facts that answer the research task.
Each finding is one short sentence with the excerpt number it comes from. Copy numbers
exactly. Reply with JSON only: {{"findings": [{{"claim": "...", "excerpt": 2}}]}}
Return {{"findings": []}} if the excerpts don't help.
{DATA_RULE}"""

FACTCHECK_SYSTEM = f"""TASK: factcheck
You are a fact-checker. For each numbered sentence of the draft, decide whether the excerpt
it cites supports it exactly (numbers, years, names). Reply with JSON only:
{{"verdicts": [{{"sentence": 1, "supported": true, "reason": ""}}]}}
{DATA_RULE}"""


@dataclass(frozen=True)
class Finding:
    claim: str
    chunk_id: str


@dataclass(frozen=True)
class Message:
    sender: str
    recipient: str
    content: str


def research_messages(task: str, hits: list[Hit], catalog: Catalog) -> list[dict[str, str]]:
    user = f"<question>{task}</question>\n<excerpts>\n{excerpts(hits, catalog)}\n</excerpts>"
    return [{"role": "system", "content": RESEARCH_SYSTEM}, {"role": "user", "content": user}]


def factcheck_messages(draft: str, hits: list[Hit], catalog: Catalog) -> list[dict[str, str]]:
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences(draft), 1))
    user = f"<draft>\n{numbered}\n</draft>\n<excerpts>\n{excerpts(hits, catalog)}\n</excerpts>"
    return [{"role": "system", "content": FACTCHECK_SYSTEM}, {"role": "user", "content": user}]


def findings_validator(hits: list[Hit]):
    def validate(data: dict) -> list[Finding]:
        out = []
        for f in data["findings"][:6]:
            n = int(f["excerpt"])
            claim = str(f["claim"]).strip()
            if claim and 1 <= n <= len(hits):
                out.append(Finding(claim[:400], hits[n - 1].chunk.id))
        return out
    return validate


def validate_verdicts(data: dict) -> dict[int, bool]:
    return {int(v["sentence"]): bool(v["supported"]) for v in data["verdicts"]}


def findings_as_notes(findings: list[Finding], hits: list[Hit]) -> str:
    marker = {h.chunk.id: n for n, h in enumerate(hits, 1)}
    lines = [f"- {f.claim.rstrip('.')} [{marker[f.chunk_id]}]" for f in findings
             if f.chunk_id in marker]
    return "Researchers' findings:\n" + "\n".join(lines) if lines else ""


class MultiAgentRag(AgenticRag):
    name = "multi_agent"
    title = "Multi-agent"
    description = (
        "An orchestrator plans research tasks; one researcher per task gathers evidence and "
        "extracts cited findings; an analyst writes the answer from the findings; a "
        "fact-checker audits every sentence and sends unsupported ones back once."
    )

    def run(self, question: str, filt: SearchFilter | None = None) -> Answer:
        trace = Trace()
        catalog = self.ctx.catalog
        inbox: list[Message] = []

        tasks = self.plan(question, filt, trace)  # the orchestrator's plan
        groups: list[list[Hit]] = []
        findings: list[Finding] = []
        facts: list = []
        previous: list[str] = []
        for i, task in enumerate(tasks, 1):
            name = f"researcher {i}"
            inbox.append(Message("orchestrator", name, task.query))
            hits, task_facts, previous = self.research(i, task, filt, previous, trace)
            with trace.step(f"{name}: extract findings") as d:
                found, ok = complete_json(
                    self.ctx.llm, research_messages(task.query, hits, catalog),
                    findings_validator(hits), [], trace,
                )
                d.update(findings=[f.claim for f in found], ok=ok)
            inbox.append(Message(name, "analyst", "; ".join(f.claim for f in found) or "nothing"))
            groups.append(hits)
            findings += found
            facts += [f for f in task_facts if f not in facts]

        # Evidence the findings rely on goes first, then the rest of each researcher's hits.
        cited = {f.chunk_id for f in findings}
        groups = [[h for h in g if h.chunk.id in cited] + [h for h in g if h.chunk.id not in cited]
                  for g in groups]
        evidence = round_robin(groups, MAX_EXCERPTS)
        notes = "\n\n".join(n for n in (findings_as_notes(findings, evidence),
                                        facts_as_notes(facts, evidence)) if n)

        with trace.step("analyst: draft answer") as d:
            draft = trace.record(generate_answer(self.ctx.llm, question, evidence, catalog,
                                                 notes=notes, model=self.answer_model)).text
            d["hits"] = summarise_hits(evidence)
        inbox.append(Message("analyst", "fact-checker", draft))

        text, rejected = self.fact_check(draft, evidence, trace)
        if rejected:
            feedback = "Rewrite without these unsupported sentences, or fix their citations: " + \
                " | ".join(rejected)
            inbox.append(Message("fact-checker", "analyst", feedback))
            with trace.step("analyst: revise"):
                revised = trace.record(generate_answer(
                    self.ctx.llm, question, evidence, catalog,
                    notes=f"{notes}\n\nFact-checker feedback: {feedback}",
                    model=self.answer_model,
                )).text
            text, _ = self.fact_check(revised, evidence, trace)

        with trace.step("messages") as d:
            d["messages"] = [m.__dict__ for m in inbox]
        return self.finish(question, text, evidence, trace)

    def fact_check(self, draft: str, evidence: list[Hit], trace: Trace) -> tuple[str, list[str]]:
        """Model verdicts first, then the deterministic check. Returns (text, rejected)."""
        if draft.strip() == NO_ANSWER:
            return draft, []
        parts = sentences(draft)
        with trace.step("fact-checker: review") as d:
            verdicts, ok = complete_json(
                self.ctx.llm, factcheck_messages(draft, evidence, self.ctx.catalog),
                validate_verdicts, {}, trace,
            )
            kept = [s for i, s in enumerate(parts, 1) if verdicts.get(i, True)]
            rejected = [s for i, s in enumerate(parts, 1) if not verdicts.get(i, True)]
            text, checks = verify_answer(" ".join(kept) or NO_ANSWER, evidence)
            rejected += [c.sentence for c in checks if c.status == "removed"]
            d.update(ok=ok, rejected=rejected,
                     checks=[{"sentence": c.sentence, "status": c.status} for c in checks])
        return text, rejected
