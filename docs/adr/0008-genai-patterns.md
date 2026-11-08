# 0008. Router, reflection and a calculator tool

Date: 2026-11-08
Status: accepted

## Context

The agent is the most accurate strategy and also the most expensive: about three model
calls per question, even for "What was Bluefin's revenue in 2024?". Agents also make two
kinds of mistakes that more retrieval doesn't fix. They forget part of the question (one
side of a comparison), and they do arithmetic in their heads.

## Decision

The `routed` strategy combines three patterns on top of the agent's plan → execute loop
(the planner–executor pattern, [ADR 0007](0007-agentic-rag.md)):

- **Router.** Rules first, because they are free and explainable. More than one company or
  year, or words like *compare*, *change*, *why*, *which company*, *the company whose*
  mean complex; short direct questions mean simple. Only long questions with no clear
  signal go to the model, with a structured `{"route": ...}` reply and "complex" as the
  safe fallback.
  - *simple* → one retrieval pass (graph-aware when the question is relational), sanitise,
    answer, verify: **one model call**
  - *complex* → the agent, with `FILINGLENS_LLM_STRONG_MODEL` for the final answer only
    (planning and assessment stay on the cheaper default model)
- **Reflection.** A critic call compares the draft with the question and lists companies
  and years the question asks about that no cited excerpt covers. Each gap gets a targeted
  search (that company, that year), and the answer is regenerated with the new evidence
  first, then verified again. Critique output is validated like every structured call:
  unknown tickers are dropped, and the fallback is "nothing missing".
- **Calculator tool.** For "how did X change from year A to year B", code extracts the
  value cited for each year from the verified answer, computes the change, and appends a
  sentence labelled `Calculated:` that cites its inputs. The model never does the
  arithmetic. Calculated sentences are excluded from the faithfulness score because their
  inputs are checked, not their wording.

## Consequences

- In demo mode it matches the agent's accuracy and injection safety at about two calls
  per question instead of three. Simple lookups cost the same as hybrid search.
- Routing rules are English-specific and hand-written. A misrouted complex question gets
  a one-pass answer, which is the hybrid strategy's quality, not a failure.
- Reflection adds a call to every complex question, and it only checks coverage.
  Correctness is still the verifier's job.
