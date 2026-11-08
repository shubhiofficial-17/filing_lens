# 0002. Ingesting 10-K filings

Date: 2026-11-08
Status: accepted

## Context

Answers are only as good as the text behind them. 10-K documents on EDGAR are large HTML
files with inline XBRL, hidden header blocks, layout tables, a table of contents that repeats
every Item heading, and financial tables where `$` and `)` sit in their own cells. CI and the
evaluation set also need data that never changes and never needs the network.

## Decision

- **One ingestion path** for every source: HTML → blocks → Item sections → store. EDGAR and
  the fixture corpus differ only in where the HTML comes from.
- **Parser on the standard library** (`html.parser`). It keeps two kinds of blocks:
  paragraphs and tables. Tables become pipe rows (`| Revenue | 1,486.2 |`) so numbers stay
  next to their labels, which matters for retrieval later. Hidden elements (`display:none`,
  the XBRL header), scripts and styles are skipped. Empty cells are dropped and `$`, `)` and
  `%` cells are merged into their neighbours.
- **Item detection**: a short paragraph matching `Item 1A.`, `ITEM 7A —`, `item 8:` and so on
  starts a section. When an Item appears more than once (table of contents, page headers),
  the occurrence followed by the most text wins.
- **Kept Items**: 1, 1A, 1C, 2, 3, 5, 7, 7A, 8, 9A. The cover page, exhibits and signatures
  add noise. A document with fewer than two Items is rejected as "not a 10-K".
- **EDGAR client** with SEC's fair-access rules built in: a contact User-Agent is required
  (the client refuses to start without one) and requests are spaced at least 120 ms apart.
  Only original 10-Ks are used; amendments (10-K/A) are skipped.
- **Fixture corpus**: three fictional companies (Northwind Robotics, Bluefin Health, Solace
  Energy), fiscal 2023–2025, generated as EDGAR-like HTML from one spec. The same spec
  generates the evaluation questions, so every expected answer is traceable to a sentence.
  One filing contains a planted prompt-injection sentence, to test guardrails later.
- **Store contract**: `InMemoryStore` and `PostgresStore`, with one test suite run against
  both (Postgres in CI). Re-ingesting a filing replaces it.

## Consequences

- The parser does not understand every EDGAR layout (for example, Items split across
  several layout tables); those documents still ingest but some sections may be merged.
- Fixture numbers are fictional, so the evaluation measures the techniques, not knowledge
  about real companies. Real filings can be ingested with `POST /api/filings/ingest`.
