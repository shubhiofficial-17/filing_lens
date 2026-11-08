# 0004. Evaluation harness

Date: 2026-11-08
Status: accepted

## Context

"It looks better" is not evidence. Every technique this project adds (hybrid search,
reranking, a graph, agents) costs latency and tokens, so each has to earn its place in
numbers, on the same questions, with the same model.

## Decision

- **A labelled set of 112 questions**, generated from the same spec as the fixture corpus,
  in ten categories: financials, people, business facts, risk factors, MD&A explanations,
  trends across years, comparisons across companies, multi-hop questions, prompt injection
  and unanswerable questions.
- **Labels are checked by a test.** Every expected string must appear in one of the
  question's gold sections, so a label can never claim something the filings don't say.
- **Metrics per answer:**
  - *accuracy*: every expected string is present and no forbidden string is present
  - *retrieval recall*: the share of gold section groups covered by retrieved chunks. A
    question that needs two filings has two groups.
  - *MRR*: the reciprocal rank of the first relevant chunk
  - *citation precision*: the share of citations pointing at a gold section or at text that
    states an expected value
  - *faithfulness*: the share of answer sentences supported by the excerpts they cite. An
    uncited sentence counts as unsupported.
  - *injection-safe*: whether the planted instruction was not repeated
  - *cost*: LLM calls, tokens, USD and latency
- **Runner:** `python -m app.eval.run` evaluates any set of strategies and writes a JSON
  report plus a Markdown table. The API serves the report at `/api/eval/report` for the
  comparison page.
- **CI gate.** The evaluation runs in CI with the demo model, and fails if a strategy drops
  below its floor in `thresholds.json`. Floors sit a few points under the measured values,
  so a regression fails the build but normal changes don't.

## Consequences

- Demo-mode numbers measure retrieval and orchestration, because the demo model is
  extractive. They are reproducible and free, but they are not the quality of a real model.
  Running with `FILINGLENS_LLM_BASE_URL` set gives real-model numbers, and the report
  records which model produced it.
- Keyword checks can mark a correct paraphrase as wrong (e.g. "$1.49 billion"). The prompt
  asks for numbers exactly as filed, which keeps this rare.
