"""Hybrid retrieval: vector + BM25, fused with Reciprocal Rank Fusion, then reranked.

Why both: vectors find paraphrases ("staff" ~ "employees"); BM25 finds exact tokens that
embeddings blur (names like "Helix Vision", numbers, "HIPAA"). RRF merges two rankings
without having to calibrate their scores against each other: score = sum(1 / (k + rank)).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from app.llm.base import LlmClient
from app.models import Hit, SearchFilter
from app.rag.catalog import Catalog
from app.rag.embeddings import Embedder
from app.store.base import Store
from app.text import terms

RRF_K = 60


def rrf(rankings: list[list[Hit]], k: int = RRF_K, limit: int = 20) -> list[Hit]:
    fused: dict[str, float] = {}
    first: dict[str, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, 1):
            fused[hit.chunk.id] = fused.get(hit.chunk.id, 0.0) + 1.0 / (k + rank)
            first.setdefault(hit.chunk.id, hit)
    ordered = sorted(fused, key=lambda cid: (-fused[cid], cid))[:limit]
    return [Hit(first[cid].chunk, fused[cid], "hybrid") for cid in ordered]


def hybrid_search(
    store: Store, embedder: Embedder, query: str, filt: SearchFilter | None, depth: int = 20
) -> tuple[list[Hit], list[Hit], list[Hit]]:
    """Returns (fused, vector hits, keyword hits)."""
    vector_hits = store.vector_search(embedder.embed([query])[0], depth, filt)
    keyword_hits = store.keyword_search(query, depth, filt)
    return rrf([vector_hits, keyword_hits], limit=depth), vector_hits, keyword_hits


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, hits: list[Hit], catalog: Catalog) -> list[Hit]: ...


class LexicalReranker:
    """A cheap cross-scorer: how much of the query a chunk covers, and how tightly.

    It sees the query and the passage together (unlike the first-stage retrievers, which
    score them separately) and rewards: coverage of query terms, coverage of rare terms,
    query terms close together, and a matching company and year in the chunk header.
    """

    name = "lexical"

    def rerank(self, query: str, hits: list[Hit], catalog: Catalog) -> list[Hit]:
        q_terms = [t for t in dict.fromkeys(terms(query)) if not t.isdigit()]
        years = {int(t) for t in terms(query) if t.isdigit() and len(t) == 4}
        tickers = set(catalog.mentioned_tickers(query))
        name_terms = {t for name in catalog.companies.values() for t in terms(name)}
        content = [t for t in q_terms if t not in name_terms]
        out = []
        for h in hits:
            words = terms(h.chunk.text)
            present = [t for t in content if t in words]
            coverage = len(present) / len(content) if content else 0.0
            score = coverage + 0.15 * _proximity(words, present)
            if tickers:
                score += 0.3 if h.chunk.ticker in tickers else -0.3
            if years:
                score += 0.2 if h.chunk.fiscal_year in years else -0.1
            score += 0.05 * h.score  # keep the fused order as a tie-breaker
            out.append(Hit(h.chunk, score, "rerank"))
        out.sort(key=lambda h: (-h.score, h.chunk.id))
        return out


def _proximity(words: list[str], present: list[str]) -> float:
    """1.0 when all matched terms fall inside a 12-word window, less when they are spread."""
    if len(present) < 2:
        return 0.0
    wanted = set(present)
    best = 0
    for i in range(len(words)):
        window = set(words[i : i + 12]) & wanted
        best = max(best, len(window))
    return best / len(wanted)


class LlmReranker:
    """Asks the model to grade each passage 0-10 for the question (a listwise judgment).

    More accurate than lexical scoring with a strong model, and much slower and costlier,
    so it is opt-in. Falls back to the input order if the reply can't be parsed."""

    name = "llm"

    def __init__(self, llm: LlmClient, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    def rerank(self, query: str, hits: list[Hit], catalog: Catalog) -> list[Hit]:
        from app.rag.prompts import rerank_messages

        reply = self._llm.complete(
            rerank_messages(query, hits, catalog), model=self._model, json_mode=True
        )
        grades = parse_grades(reply.text, len(hits))
        if grades is None:
            return hits
        ranked = sorted(range(len(hits)), key=lambda i: (-grades[i], i))
        return [Hit(hits[i].chunk, grades[i], "rerank") for i in ranked]


def parse_grades(text: str, n: int) -> list[float] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        grades = [0.0] * n
        for item in data.get("grades", []):
            i = int(item["passage"]) - 1
            if 0 <= i < n:
                grades[i] = float(item["score"])
        return grades
    except (ValueError, KeyError, TypeError):
        return None


def select_with_coverage(
    hits: list[Hit], k: int, groups: list[tuple[str, int | None]]
) -> list[Hit]:
    """Top-k, but first make sure each (ticker, year) the question asks about is represented.

    A comparison of two companies needs evidence for both; plain top-k often returns five
    chunks about whichever company matches the wording best."""
    chosen: list[Hit] = []
    for ticker, year in groups:
        for h in hits:
            if h.chunk.ticker == ticker and (year is None or h.chunk.fiscal_year == year):
                if h not in chosen:
                    chosen.append(h)
                break
    for h in hits:
        if len(chosen) >= k:
            break
        if h not in chosen:
            chosen.append(h)
    order = {id(h): i for i, h in enumerate(hits)}
    return sorted(chosen[:k], key=lambda h: order[id(h)])


def coverage_groups(filt: SearchFilter) -> list[tuple[str, int | None]]:
    tickers = filt.tickers or ()
    years = filt.years or ()
    if len(tickers) <= 1 and len(years) <= 1:
        return []
    if tickers and years:
        return [(t, y) for t in tickers for y in years]
    if tickers:
        return [(t, None) for t in tickers]
    return []
