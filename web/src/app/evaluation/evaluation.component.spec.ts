import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ApiService } from '../shared/api.service';
import { EvalReport, Metrics } from '../shared/models';
import { EvaluationComponent } from './evaluation.component';

function metrics(accuracy: number, calls: number): Metrics {
  return {
    questions: 10, accuracy, keyword_recall: accuracy, retrieval_recall: 0.9, mrr: 0.8,
    citation_precision: 0.9, faithfulness: 1, injection_safe: null, llm_calls: calls,
    tokens: 600, cost_usd: 0, latency_p50_ms: 2, latency_p95_ms: 3,
  };
}

const REPORT: EvalReport = {
  generated_at: '2026-11-08T00:00:00Z', model: 'demo (not an AI)', embedder: 'hashing-256',
  demo_mode: true, questions: 10,
  strategies: {
    naive: { title: 'Naive RAG', description: 'd', overall: metrics(0.5, 1),
             by_category: { financials: { questions: 5, accuracy: 0.6 } }, misses: [] },
    agentic: { title: 'Agentic RAG', description: 'd', overall: metrics(0.9, 3),
               by_category: { financials: { questions: 5, accuracy: 1 } }, misses: [] },
  },
};

describe('EvaluationComponent', () => {
  it('shows strategies in report order and highlights the best value', () => {
    TestBed.configureTestingModule({
      imports: [EvaluationComponent],
      providers: [{ provide: ApiService, useValue: { evalReport: () => of(REPORT) } }],
    });
    const fixture = TestBed.createComponent(EvaluationComponent);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const rows = Array.from(el.querySelectorAll('section:first-of-type tbody tr'));
    expect(rows.map((r) => r.querySelector('strong')?.textContent)).toEqual(['Naive RAG', 'Agentic RAG']);
    expect(rows[1].querySelector('td.best')?.textContent?.trim()).toBe('90.0%');
    expect(el.textContent).toContain('not an AI');
  });
});
