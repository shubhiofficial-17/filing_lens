export interface Strategy {
  name: string;
  title: string;
  description: string;
}

export interface Citation {
  marker: number;
  chunk_id: string;
  filing_id: string;
  ticker: string;
  fiscal_year: number;
  item: string;
  quote: string;
  supported: boolean;
}

export interface Retrieved {
  chunk_id: string;
  ticker: string;
  fiscal_year: number;
  item: string;
  kind: string;
  score: number;
  source: string;
  text: string;
}

export interface TraceStep {
  name: string;
  detail: string;
  data: Record<string, unknown>;
  ms: number;
}

export interface Usage {
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface Answer {
  question: string;
  strategy: string;
  text: string;
  citations: Citation[];
  retrieved: Retrieved[];
  trace: TraceStep[];
  usage: Usage;
  model: string;
  latency_ms: number;
}

export interface AskRequest {
  question: string;
  strategy: string;
  tickers?: string[];
  years?: number[];
}

export interface Filing {
  id: string;
  ticker: string;
  company: string;
  cik: string;
  fiscal_year: number;
  form: string;
  filed_on: string;
  source_url: string;
}

export interface FilingDetail extends Filing {
  sections: { id: string; item: string; title: string; words: number }[];
}

export interface Section {
  id: string;
  filing_id: string;
  item: string;
  title: string;
  text: string;
}

export interface Metrics {
  questions: number;
  accuracy: number | null;
  keyword_recall: number | null;
  retrieval_recall: number | null;
  mrr: number | null;
  citation_precision: number | null;
  faithfulness: number | null;
  injection_safe: number | null;
  llm_calls: number | null;
  tokens: number | null;
  cost_usd: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
}

export interface StrategyReport {
  title: string;
  description: string;
  overall: Metrics;
  by_category: Record<string, { questions: number; accuracy: number | null }>;
  misses: { id: string; missing: string[]; answer: string }[];
}

export interface EvalReport {
  generated_at: string;
  model: string;
  embedder: string;
  demo_mode: boolean;
  questions: number;
  strategies: Record<string, StrategyReport>;
}
