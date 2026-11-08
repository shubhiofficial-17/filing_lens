# 0009. Multi-agent research: find, write, check

Date: 2026-11-08
Status: accepted

## Context

One agent that searches, writes and checks its own work tends to believe itself. Separating
roles is a common answer, and a common source of cost without benefit. So it goes in as one
more strategy, measured on the same questions as the rest, not as the default.

## Decision

`multi_agent` reuses the agent's planner and retrieval, and splits the work into roles that
talk only through recorded messages:

- **Orchestrator**: the plan from [ADR 0007](0007-agentic-rag.md). One research task per
  company, year or hop.
- **Researchers** (one per task): retrieve and sanitise their own evidence, then extract
  *findings*. Each finding is one short claim tied to an excerpt number; claims pointing at
  an excerpt that doesn't exist are dropped. Researchers never see each other's evidence.
- **Analyst**: writes the answer from the findings (passed as notes), with excerpts the
  findings rely on placed first. The analyst never searches.
- **Fact-checker**: model verdicts per sentence, then the deterministic citation check.
  Rejected sentences go back to the analyst *once* with the reasons. After the revision,
  whatever still fails is removed.

Every message (orchestrator → researcher, researcher → analyst, analyst → fact-checker,
fact-checker → analyst) is stored in the trace, and the UI shows them as a conversation.

## Consequences

- In demo mode it is slightly *less* accurate than the single agent (about 92% against
  94%), at about five calls per question instead of three. The demo model is extractive,
  so splitting roles buys little. A real model, which can misread or overstate, is
  where an independent checker earns its cost. That is a hypothesis to test with real-model
  runs, not a claim.
- The architecture is the reusable part: narrow prompts, explicit hand-offs, bounded
  revision, and a deterministic backstop under the model's own checking.
