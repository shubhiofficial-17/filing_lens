# 0005. Hybrid search, reranking and query understanding

Date: 2026-11-08
Status: accepted

## Context

The naive baseline misses in predictable ways. It finds "headquartered in Pittsburgh" for a
question about Northwind's CFO, because the company name dominates the similarity and "CFO"
never appears in the filing. It returns five chunks about one company when the question
compares two. And it ignores exact tokens such as "HIPAA" or "Helix Vision" when the
embedding blurs them.

## Decision

The `hybrid` strategy adds four steps, each visible in the trace:

1. **Query understanding.** Companies (from names, short names and tickers in the catalog)
   and fiscal years that exist in the corpus become metadata filters. Filters set by the
   caller win. A **glossary rewrite** appends filing vocabulary to the query ("CEO" → "chief
   executive officer", "profit" → "net income", "headcount" → "full-time employees").
2. **Two retrievers.** Vector search and keyword search, 20 candidates each. In memory,
   keyword search is BM25 (k1 = 1.2, b = 0.75). In Postgres it is a generated `tsvector`
   column with a GIN index, an OR-query and `ts_rank_cd` with length normalisation. Query
   words are reduced to `[a-z0-9]` before building the `tsquery`, so user input can't break
   its syntax.
3. **Reciprocal Rank Fusion** (k = 60). It fuses ranks, not scores, so cosine similarity
   and BM25 never have to be calibrated against each other.
4. **Rerank, then select with coverage.** A lexical cross-scorer looks at query and passage
   together: coverage of content words, proximity of matched words, and matching company
   and year. An `LlmReranker` (the model grades passages 0–10, with JSON parsed defensively)
   is available but not the default, because it adds a model call per question. The final
   top-k first reserves one slot for each (company, year) the question asks about, so a
   comparison always has evidence for both sides.

If inferred filters return nothing (for example a year the corpus doesn't have), the search
runs again without them.

## Consequences

- In demo mode: retrieval recall goes from about 82% to 99% and accuracy from about 58% to
  89% (see `docs/evaluation.md`), at the same single model call per question.
- Two queries per question instead of one. Both are indexed, and the cost is milliseconds.
- The glossary is small and hand-written. The agentic strategy adds model-written rewrites
  for vocabulary the glossary doesn't cover.
