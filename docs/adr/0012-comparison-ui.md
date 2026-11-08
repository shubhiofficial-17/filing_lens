# 0012. A UI built for comparing strategies

Date: 2026-11-08
Status: accepted

## Context

The interesting output of this project is not one answer but how strategies differ: which
evidence each found, what it cost, where it went wrong. The UI should make that visible
without opening the API docs.

## Decision

Three pages (Angular 18 standalone components, signals, OnPush, strict templates):

- **Ask**: a question, a strategy picker (from `/api/strategies`, with its description),
  and example questions that show each strategy's strengths and weaknesses. **Compare all
  strategies** runs the same question through every strategy *sequentially*, since they
  share the model endpoint and its rate limits, and shows the answers side by side, each
  with its own error state.
- **Answer view**: citation markers are buttons that highlight their source. The sources
  list shows each citation's quote and flags unsupported ones. Two collapsible panels show
  the excerpts the model saw (with retrieval source and score) and the full trace: every
  step with its timing and data, including plans, sanitised sentences, agent messages and
  fact-checks.
- **Evaluation**: the latest report from `/api/eval/report`. One row per strategy with the
  best value in each metric highlighted, accuracy by question type, and a visible note
  when the numbers come from the demo model.
- **Filings**: browse filings and their Items, and ingest a ticker from EDGAR.

## Consequences

- No UI library. Shared styles live in `styles.css` and each component has a few lines of
  its own, so the bundle stays small and the CSP stays strict for scripts.
- Traces are shown as raw JSON per step. That is less pretty than a custom view, but every
  strategy's trace data stays visible without per-strategy UI code.
