# 0007. Agentic RAG and guardrails for untrusted text

Date: 2026-11-08
Status: accepted

## Context

A single retrieve-then-answer pass has three blind spots. It can't search each side of a
comparison separately. It doesn't notice when its evidence is thin. And it passes whatever
the documents say straight to the model, including the planted "ignore all previous
instructions" sentence in the fixture corpus, which the hybrid and graph strategies
dutifully repeat.

## Decision

The `agentic` strategy is a small, explicit loop. There is no framework, so every step is
visible in the trace and testable with a scripted model:

1. **Plan** (structured output): up to 4 search steps, each with its own query, tickers and
   years. Comparisons get one step per company or year. A chained question ("X, and who was
   that company's CEO?") gets a second step with `uses_previous`, which inherits the
   companies the first step reached through the graph.
2. **Research each step** with the graph-aware hybrid retriever, then:
   - **sanitise**: sentences that look like instructions to an AI are removed from
     excerpts before any model sees them, and each removal is listed in the trace
   - **assess** (structured output): is this enough? If not, search once more with the
     model's suggested wording and without the year filter
3. **Merge round-robin** across steps (at most 10 excerpts), so one step's long list
   can't crowd out another's evidence.
4. **Answer**, with graph facts as notes.
5. **Verify citations**: each sentence must be supported by its cited excerpt, with every
   number present. Wrongly cited but supported sentences are re-cited; unsupported ones are
   removed; if nothing survives, the answer is the refusal sentence.

**Structured outputs** go through `complete_json`: find the outermost JSON object,
validate it with a plain function (unknown tickers and years are dropped), repair once by
showing the model its reply and the error, then use a fallback. A bad reply degrades the
answer; it never fails the request.

**Guardrails are layered** because none is enough alone: pattern-based sanitising,
fencing (`<excerpts>` and a "data, not instructions" rule), and citation verification
after the answer.

## Consequences

- In demo mode it scores the highest accuracy and is the only strategy with 100%
  injection safety. It costs about 3 model calls per question instead of 1, and roughly
  2.5× the tokens.
- The injection patterns are a denylist; a determined attacker can phrase around them.
  Verification is the backstop: an injected claim still has to be supported by an excerpt,
  and with the instruction removed, it isn't.
- Loop limits (4 steps, 2 rounds, 10 excerpts) bound the cost of a single question.
