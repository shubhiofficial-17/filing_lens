# 0006. GraphRAG: a knowledge graph next to the text index

Date: 2026-11-08
Status: accepted

## Context

Some questions are about relationships, not passages. Take "Which company owns Helix Vision
Ltd., and who was that company's CEO?" or "What was the revenue of the company whose
largest customer is Keystone Health Plan?". The question doesn't name the company to search
for. Text retrieval has to find the ownership sentence and the CEO sentence by luck, in one
query.

## Decision

- **Extraction at ingest time.** Each text chunk goes through an `Extractor` that returns
  entities (company, organisation, person) and relations: CEO, CFO, OWNS, ACQUIRED,
  COMPETES_WITH, CUSTOMER and SUCCEEDED.
  - `RuleExtractor` (default): patterns for the sentences 10-Ks use for these facts. It is
    deterministic and free, and precise on the phrasings it knows.
  - `LlmExtractor`: one model call per chunk, returning JSON triples. Replies are validated:
    unknown relation types and malformed items are dropped.
- **Provenance on every relation**: filing, fiscal year and chunk id. A graph fact is always
  cited back to the sentence it came from, so graph answers are as checkable as text
  answers.
- **Entity ids** are normalised names without corporate suffixes ("Bluefin Health Corp." →
  `bluefin health`). Ltd, GmbH, LLC and similar suffixes stay in the id, because they tell
  a subsidiary from its parent (`northwind robotics gmbh` vs `northwind robotics`). Each
  entity also gets a short alias for matching questions ("Helix Vision"), unless that alias
  is another entity's id.
- **Storage** sits next to the text index in the same database (`entities`, `relations`),
  not in a separate graph database. Two hops over a few thousand edges per company is one
  indexed query. Re-ingesting a filing replaces its relations.
- **Answer time** (`graph` strategy):
  1. Find the entities the question mentions (longest alias first).
  2. Hop 1: facts touching them. Hop 2: facts of the *companies* hop 1 reached, limited to
     relation types the question asks about ("CEO", "subsidiary", "customer" and so on).
  3. Keep facts the question is about: a relation it asks for, or an entity it names other
     than the filing company. Asking about Northwind's revenue does not pull in every
     Northwind fact.
  4. Companies the graph reached become the search filter when the question named none.
  5. Hybrid retrieval as before. The facts' source chunks go first in the context, and the
     facts themselves go into the prompt as notes with `[n]` markers pointing at those
     chunks.

## Consequences

- In demo mode, multi-hop accuracy rises from about 43% (hybrid) to about 86%, with no extra
  model calls at question time. The cost moves to ingest time (zero for rules, one call per
  chunk for the LLM extractor).
- The rule extractor does not generalise to arbitrary phrasings in real filings. Use the
  LLM extractor there, ideally through the gateway's cache, since extraction is
  re-runnable.
- Entity resolution is name-based. "Helix Vision" and "Helix Vision Limited" would merge,
  but a renamed company would not.
