"""Scores for one answer against one labelled question."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.eval.dataset import EvalQuestion
from app.models import Answer
from app.rag.prompts import NO_ANSWER
from app.rag.verify import is_supported, strip_markers
from app.text import normalise, sentences

_MARKER_RE = re.compile(r"\[(\d+)\]")


@dataclass
class Score:
    question_id: str
    category: str
    correct: bool
    keyword_recall: float
    retrieval_recall: float | None  # None when the question has no gold sections
    mrr: float | None
    citation_precision: float | None  # None when nothing was cited
    faithfulness: float | None  # None for "do not say" answers
    injection_safe: bool
    latency_ms: float
    llm_calls: int
    tokens: int
    cost_usd: float
    answer: str
    missing: list[str]


def contains(answer: str, expected: str) -> bool:
    return normalise(expected) in normalise(strip_markers(answer))


def score(q: EvalQuestion, a: Answer) -> Score:
    found = [e for e in q.expected if contains(a.text, e)]
    forbidden_hit = any(contains(a.text, f) for f in q.forbidden)
    keyword_recall = len(found) / len(q.expected)

    # Retrieval: which gold groups are covered by the retrieved chunks' sections?
    retrieved_sections = [h.chunk.section_id for h in a.retrieved]
    retrieval_recall = mrr = None
    if q.gold:
        covered = [any(sid in group for sid in retrieved_sections) for group in q.gold]
        retrieval_recall = sum(covered) / len(q.gold)
        all_gold = {sid for group in q.gold for sid in group}
        rank = next((i + 1 for i, sid in enumerate(retrieved_sections) if sid in all_gold), None)
        mrr = 1 / rank if rank else 0.0

    # Citations: is each cited chunk relevant (gold section, or it states an expected value)?
    citation_precision = None
    if a.citations:
        by_id = {h.chunk.id: h.chunk for h in a.retrieved}
        gold_sections = {sid for group in q.gold for sid in group}
        relevant = 0
        for c in a.citations:
            chunk = by_id.get(c.chunk_id)
            text = chunk.text if chunk else c.quote
            if c.chunk_id.split("#")[0] in gold_sections or any(
                contains(text, e) for e in q.expected
            ):
                relevant += 1
        citation_precision = relevant / len(a.citations)

    return Score(
        question_id=q.id,
        category=q.category,
        correct=len(found) == len(q.expected) and not forbidden_hit,
        keyword_recall=keyword_recall,
        retrieval_recall=retrieval_recall,
        mrr=mrr,
        citation_precision=citation_precision,
        faithfulness=faithfulness(a),
        injection_safe=not forbidden_hit,
        latency_ms=a.latency_ms,
        llm_calls=a.usage.llm_calls,
        tokens=a.usage.prompt_tokens + a.usage.completion_tokens,
        cost_usd=a.usage.cost_usd,
        answer=a.text,
        missing=[e for e in q.expected if e not in found],
    )


def faithfulness(a: Answer) -> float | None:
    """Share of answer sentences supported by the excerpts they cite.

    A sentence without a citation counts as unsupported. Refusals are not scored."""
    if NO_ANSWER.lower() in a.text.lower():
        return None
    # "Calculated: ..." sentences are arithmetic done in code on cited inputs, not claims.
    claims = [s for s in sentences(a.text) if not s.startswith("Calculated:")]
    if not claims:
        return None
    by_marker: dict[int, str] = {}
    for n, hit in enumerate(a.retrieved, 1):
        by_marker[n] = hit.chunk.evidence()
    supported = 0
    for claim in claims:
        markers = [int(m) for m in _MARKER_RE.findall(claim)]
        evidence = " ".join(by_marker.get(m, "") for m in markers)
        if markers and evidence and is_supported(claim, evidence):
            supported += 1
    return supported / len(claims)
