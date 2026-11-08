"""Answering strategies. Each one turns a question into a cited Answer with a trace.

They share one context (store, embedder, model, catalog) and differ only in how they find
and use evidence, so the evaluation can compare them on equal terms.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.base import LlmClient
from app.models import Answer, Hit, SearchFilter
from app.rag.answer import generate_answer, parse_citations
from app.rag.catalog import Catalog
from app.rag.embeddings import Embedder
from app.rag.trace import Trace
from app.store.base import Store


@dataclass
class RagContext:
    store: Store
    embedder: Embedder
    llm: LlmClient
    top_k: int = 5
    strong_model: str | None = None
    _catalog: Catalog | None = field(default=None, repr=False)
    _catalog_size: int = -1

    @property
    def catalog(self) -> Catalog:
        size = self.store.count_filings()
        if self._catalog is None or size != self._catalog_size:
            self._catalog = Catalog.build(self.store)
            self._catalog_size = size
        return self._catalog


def summarise_hits(hits: list[Hit]) -> list[dict]:
    return [{"chunk": h.chunk.id, "score": round(h.score, 4), "source": h.source} for h in hits]


class Pipeline:
    name = "base"
    title = ""
    description = ""

    def __init__(self, ctx: RagContext) -> None:
        self.ctx = ctx

    def run(self, question: str, filt: SearchFilter | None = None) -> Answer:
        raise NotImplementedError

    def finish(self, question: str, text: str, hits: list[Hit], trace: Trace) -> Answer:
        return Answer(
            question=question,
            strategy=self.name,
            text=text,
            citations=parse_citations(text, hits),
            retrieved=hits,
            trace=trace.steps,
            usage=trace.usage,
            model=trace.model,
            latency_ms=trace.elapsed_ms(),
        )


class NaiveRag(Pipeline):
    name = "naive"
    title = "Naive RAG"
    description = "Embed the question, take the top-k chunks by vector similarity, answer."

    def run(self, question: str, filt: SearchFilter | None = None) -> Answer:
        trace = Trace()
        with trace.step("embed question", self.ctx.embedder.name):
            vector = self.ctx.embedder.embed([question])[0]
        with trace.step("vector search", f"top {self.ctx.top_k}") as d:
            hits = self.ctx.store.vector_search(vector, self.ctx.top_k, filt)
            d["hits"] = summarise_hits(hits)
        with trace.step("generate answer"):
            completion = trace.record(
                generate_answer(self.ctx.llm, question, hits, self.ctx.catalog)
            )
        return self.finish(question, completion.text, hits, trace)


def merge_filters(inferred: SearchFilter, given: SearchFilter | None) -> SearchFilter:
    """Filters the caller set win; filters inferred from the question fill the gaps."""
    if given is None:
        return inferred
    return SearchFilter(
        tickers=given.tickers or inferred.tickers,
        years=given.years or inferred.years,
        items=given.items or inferred.items,
    )


class HybridRag(Pipeline):
    name = "hybrid"
    title = "Hybrid + rerank"
    description = (
        "Query understanding (companies, years, glossary rewrite), vector + BM25 search fused "
        "with reciprocal rank fusion, reranked, with coverage for every company and year asked."
    )

    def retrieve(self, question: str, filt: SearchFilter | None, trace: Trace) -> list[Hit]:
        from app.rag.query import rewrite
        from app.rag.retrieval import (
            LexicalReranker,
            coverage_groups,
            hybrid_search,
            select_with_coverage,
        )

        catalog = self.ctx.catalog
        with trace.step("understand question") as d:
            inferred = merge_filters(catalog.understand(question), filt)
            query = rewrite(question)
            d.update(tickers=list(inferred.tickers or []), years=list(inferred.years or []),
                     query=query)
        with trace.step("hybrid search", "vector + BM25, reciprocal rank fusion") as d:
            fused, vec, kw = hybrid_search(self.ctx.store, self.ctx.embedder, query, inferred)
            if not fused and (inferred.tickers or inferred.years):
                # The inferred filter was too strict (e.g. a year we don't have): search wide.
                fused, vec, kw = hybrid_search(self.ctx.store, self.ctx.embedder, query, filt)
            d.update(vector=len(vec), keyword=len(kw), fused=summarise_hits(fused[:10]))
        reranker = LexicalReranker()
        with trace.step("rerank", reranker.name) as d:
            ranked = reranker.rerank(query, fused, catalog)
            hits = select_with_coverage(ranked, self.ctx.top_k, coverage_groups(inferred))
            d["hits"] = summarise_hits(hits)
        return hits

    def run(self, question: str, filt: SearchFilter | None = None) -> Answer:
        trace = Trace()
        hits = self.retrieve(question, filt, trace)
        with trace.step("generate answer"):
            completion = trace.record(
                generate_answer(self.ctx.llm, question, hits, self.ctx.catalog)
            )
        return self.finish(question, completion.text, hits, trace)
