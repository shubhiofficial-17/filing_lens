# Evaluation results

112 labelled questions over the fixture corpus · model: demo model (deterministic, not an AI) · embedder: hashing-256 · generated 2026-11-08T18:26:29Z

| Strategy | Accuracy | Retrieval recall | MRR | Citation precision | Faithfulness | Injection-safe | LLM calls | Tokens | p50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Naive RAG | 58.0% | 81.8% | 62.0% | 75.3% | 100.0% | 50.0% | 1.0 | 644 | 2 |
| Hybrid + rerank | 89.3% | 99.1% | 91.4% | 88.3% | 100.0% | 50.0% | 1.0 | 715 | 1 |
| GraphRAG | 92.9% | 100.0% | 91.0% | 91.1% | 100.0% | 50.0% | 1.0 | 805 | 2 |
| Agentic RAG | 93.8% | 100.0% | 91.0% | 90.6% | 100.0% | 100.0% | 3.1 | 1,841 | 3 |
| Router + reflection | 93.8% | 100.0% | 91.0% | 90.6% | 100.0% | 100.0% | 2.0 | 1,506 | 2 |
| Multi-agent | 92.0% | 100.0% | 95.5% | 87.9% | 100.0% | 100.0% | 5.2 | 3,525 | 3 |
| MCP tool agent | 92.9% | 100.0% | 92.7% | 94.0% | 100.0% | 100.0% | 3.2 | 2,388 | 2 |

## Accuracy by question type

| Strategy | business | comparisons | financials | injection | mdna | multi_hop | people | risks | trends | unanswerable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Naive RAG | 61.1% | 40.0% | 72.2% | 0.0% | 16.7% | 14.3% | 72.2% | 50.0% | 50.0% | 100.0% |
| Hybrid + rerank | 100.0% | 80.0% | 100.0% | 50.0% | 66.7% | 42.9% | 100.0% | 66.7% | 100.0% | 100.0% |
| GraphRAG | 100.0% | 80.0% | 100.0% | 50.0% | 83.3% | 85.7% | 100.0% | 66.7% | 100.0% | 100.0% |
| Agentic RAG | 100.0% | 80.0% | 100.0% | 100.0% | 83.3% | 85.7% | 100.0% | 66.7% | 100.0% | 100.0% |
| Router + reflection | 100.0% | 80.0% | 100.0% | 100.0% | 83.3% | 85.7% | 100.0% | 66.7% | 100.0% | 100.0% |
| Multi-agent | 100.0% | 80.0% | 100.0% | 100.0% | 83.3% | 85.7% | 100.0% | 66.7% | 66.7% | 100.0% |
| MCP tool agent | 100.0% | 80.0% | 100.0% | 100.0% | 66.7% | 85.7% | 100.0% | 66.7% | 100.0% | 100.0% |
