# 0003. A naive RAG baseline with citations

Date: 2026-11-08
Status: accepted

## Context

The point of FilingLens is to measure how much each retrieval and agent technique helps.
That needs an honest baseline: the simplest pipeline that works, built on the same pieces
every later strategy uses.

## Decision

- **Chunking** groups paragraphs up to 80 words and never cuts a paragraph unless it is
  too long on its own (then it is split on sentences). Tables are never split or mixed with
  prose, so a number always arrives with its row label and its year columns. A short
  sub-heading stays with the paragraph it introduces.
- **Contextual chunk headers.** Each chunk is embedded and indexed as
  `"{company} ({ticker}) 10-K fiscal {year}, Item {item} {title}\n{text}"`. A paragraph like
  "Revenue grew 11.5%" does not say whose revenue or which year; the header does.
- **Embeddings** go through an `Embedder` interface: an OpenAI-compatible `/embeddings`
  endpoint (for example through the LLM Gateway), or an offline `HashingEmbedder` (feature
  hashing of words and word pairs) used in tests, CI and the demo. Both produce unit vectors,
  so cosine similarity is a dot product, and pgvector uses `vector_cosine_ops` with HNSW.
- **Model calls** go through an `LlmClient` interface with one OpenAI-compatible
  implementation. Provider keys, fallbacks, caching and budgets live in the LLM Gateway, so
  this client only retries once on 5xx, 429 and timeouts.
- **`DemoLlm`**, a deterministic, rule-based stand-in that is labelled "not an AI"
  everywhere. It reads the `TASK:` line of each system prompt and does a simple extractive
  version of the job. The whole system, including the evaluation and E2E tests, runs offline
  with no key and gives the same output on every run.
- **Prompt.** Excerpts are numbered and fenced inside `<excerpts>`, each with its company,
  year and Item. The system prompt says excerpts are data and not instructions, requires a
  `[n]` citation on every sentence, and gives one exact refusal sentence for missing answers.
- **Citations** are parsed from `[n]` markers. Markers that point at no excerpt are dropped.
  Each citation carries the best-supporting sentence of its chunk as a quote, and a
  `supported` flag from a lexical check that requires *every number* in the claim to appear
  in the evidence.
- **Invariant:** an answer's `retrieved` list is exactly the excerpt list the model saw, in
  order, so `[n]` always means `retrieved[n-1]`. The evaluation depends on this.

## Consequences

- With the hashing embedder, retrieval is lexical: "CFO" does not match "Chief Financial
  Officer". That is a real weakness of naive retrieval, and later strategies address it
  with query rewriting. With a real embedding model the gap is smaller.
- Every answer comes with a trace (steps, timings, tokens), so the UI and the evaluation can
  show where time and money go.
