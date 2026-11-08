# Evaluation results

112 labelled questions over the fixture corpus · model: demo model (deterministic, not an AI) · embedder: hashing-256 · generated 2026-11-08T17:58:25Z

| Strategy | Accuracy | Retrieval recall | MRR | Citation precision | Faithfulness | Injection-safe | LLM calls | Tokens | p50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Naive RAG | 50.9% | 81.8% | 61.7% | 79.6% | 100.0% | 100.0% | 1.0 | 631 | 2 |

## Accuracy by question type

| Strategy | business | comparisons | financials | injection | mdna | multi_hop | people | risks | trends | unanswerable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Naive RAG | 61.1% | 20.0% | 61.1% | 0.0% | 0.0% | 14.3% | 72.2% | 33.3% | 50.0% | 100.0% |
