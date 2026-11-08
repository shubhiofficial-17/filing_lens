"""Generate a cited answer from retrieved chunks, and turn [n] markers into citations."""

from __future__ import annotations

import re

from app.llm.base import Completion, LlmClient
from app.models import Citation, Hit
from app.rag.catalog import Catalog
from app.rag.prompts import answer_messages
from app.rag.verify import best_quote, is_supported, strip_markers
from app.text import sentences

_MARKER_RE = re.compile(r"\[(\d+)\]")


def generate_answer(
    llm: LlmClient, question: str, hits: list[Hit], catalog: Catalog, *, notes: str = "",
    model: str | None = None,
) -> Completion:
    return llm.complete(answer_messages(question, hits, catalog, notes=notes), model=model)


def parse_citations(answer: str, hits: list[Hit]) -> list[Citation]:
    """One citation per distinct marker. Markers pointing at no excerpt are dropped.

    `supported` records whether the sentence carrying the marker is backed by that excerpt.
    """
    out: dict[int, Citation] = {}
    for sentence in sentences(answer):
        for m in _MARKER_RE.finditer(sentence):
            n = int(m.group(1))
            if n in out or not 1 <= n <= len(hits):
                continue
            chunk = hits[n - 1].chunk
            claim = strip_markers(sentence)
            out[n] = Citation(
                marker=n,
                chunk_id=chunk.id,
                filing_id=chunk.filing_id,
                ticker=chunk.ticker,
                fiscal_year=chunk.fiscal_year,
                item=chunk.item,
                quote=best_quote(claim, chunk.text),
                supported=is_supported(claim, chunk.text),
            )
    return [out[k] for k in sorted(out)]


def renumber(answer: str, hits: list[Hit], cited_ids: list[str]) -> str:
    """Rewrite markers after the excerpt list was rebuilt (used when merging agent answers)."""
    position = {cid: i + 1 for i, cid in enumerate(cited_ids)}

    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        if not 1 <= n <= len(hits):
            return ""
        return f"[{position.get(hits[n - 1].chunk.id, n)}]"

    return _MARKER_RE.sub(repl, answer)
