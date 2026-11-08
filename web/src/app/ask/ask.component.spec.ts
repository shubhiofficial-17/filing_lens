import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { ApiService } from '../shared/api.service';
import { Answer, AskRequest, Strategy } from '../shared/models';
import { AskComponent } from './ask.component';

const STRATEGIES: Strategy[] = [
  { name: 'naive', title: 'Naive RAG', description: 'Plain vector search.' },
  { name: 'routed', title: 'Router + reflection', description: 'Routes questions.' },
];

function answer(strategy: string): Answer {
  return {
    question: 'q',
    strategy,
    text: 'Revenue was $905.7 million [1].',
    citations: [
      {
        marker: 1, chunk_id: 'BFHC-2024-10K:7#0', filing_id: 'BFHC-2024-10K', ticker: 'BFHC',
        fiscal_year: 2024, item: '7', quote: 'Total revenue was $905.7 million.', supported: true,
      },
    ],
    retrieved: [
      {
        chunk_id: 'BFHC-2024-10K:7#0', ticker: 'BFHC', fiscal_year: 2024, item: '7', kind: 'text',
        score: 0.9, source: 'hybrid', text: 'Total revenue was $905.7 million.',
      },
    ],
    trace: [{ name: 'hybrid search', detail: '', data: { hits: 1 }, ms: 1.5 }],
    usage: { llm_calls: 1, prompt_tokens: 100, completion_tokens: 20, cost_usd: 0 },
    model: 'demo (not an AI)',
    latency_ms: 12,
  };
}

describe('AskComponent', () => {
  let asked: AskRequest[];

  function setup(fail: string | null = null): HTMLElement {
    asked = [];
    const api: Partial<ApiService> = {
      strategies: () => of(STRATEGIES),
      ask: (body: AskRequest) => {
        asked.push(body);
        return body.strategy === fail
          ? throwError(() => ({ status: 502, error: { detail: 'the model is unavailable' } }))
          : of(answer(body.strategy));
      },
    };
    TestBed.configureTestingModule({
      imports: [AskComponent],
      providers: [{ provide: ApiService, useValue: api }],
    });
    const fixture = TestBed.createComponent(AskComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.question = 'What was Bluefin revenue in 2024?';
    return Object.assign(fixture.nativeElement as HTMLElement, { component, fixture });
  }

  it('asks with the selected strategy and renders cited answers', () => {
    const el = setup() as HTMLElement & { component: AskComponent; fixture: { detectChanges(): void } };
    el.component.ask();
    el.fixture.detectChanges();
    expect(asked).toEqual([{ question: 'What was Bluefin revenue in 2024?', strategy: 'routed' }]);
    expect(el.querySelector('.answer')?.textContent).toContain('Revenue was $905.7 million');
    expect(el.querySelector('button.marker')?.textContent?.trim()).toBe('1');
    expect(el.querySelector('.sources')?.textContent).toContain('BFHC 2024');
  });

  it('compares every strategy and shows errors per strategy', () => {
    const el = setup('naive') as HTMLElement & { component: AskComponent; fixture: { detectChanges(): void } };
    el.component.compareAll();
    el.fixture.detectChanges();
    expect(asked.map((a) => a.strategy)).toEqual(['naive', 'routed']);
    const cards = el.querySelectorAll('article');
    expect(cards.length).toBe(2);
    expect(cards[0].textContent).toContain('the model is unavailable');
    expect(cards[1].querySelector('.answer')).not.toBeNull();
  });
});
