import { DecimalPipe, KeyValuePipe, PercentPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';

import { ApiService, errorMessage } from '../shared/api.service';
import { EvalReport, Metrics } from '../shared/models';

type MetricKey = keyof Metrics;

const COLUMNS: { key: MetricKey; label: string; kind: 'pct' | 'num' }[] = [
  { key: 'accuracy', label: 'Accuracy', kind: 'pct' },
  { key: 'retrieval_recall', label: 'Retrieval recall', kind: 'pct' },
  { key: 'mrr', label: 'MRR', kind: 'pct' },
  { key: 'citation_precision', label: 'Citation precision', kind: 'pct' },
  { key: 'faithfulness', label: 'Faithfulness', kind: 'pct' },
  { key: 'injection_safe', label: 'Injection-safe', kind: 'pct' },
  { key: 'llm_calls', label: 'Model calls', kind: 'num' },
  { key: 'tokens', label: 'Tokens', kind: 'num' },
];

@Component({
  selector: 'app-evaluation',
  standalone: true,
  imports: [DecimalPipe, PercentPipe, KeyValuePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (error()) {
      <p class="error" role="alert">{{ error() }}</p>
    }
    @if (report(); as r) {
      <section class="panel">
        <h2>How the strategies compare</h2>
        <p class="small muted">
          {{ r.questions }} labelled questions over the fixture corpus · model:
          {{ r.demo_mode ? 'demo model (deterministic, not an AI)' : r.model }} · embedder:
          {{ r.embedder }} · {{ r.generated_at }}
        </p>
        @if (r.demo_mode) {
          <p class="small note">
            Demo-mode numbers measure retrieval and orchestration: the demo model only extracts
            sentences. Run the evaluation with a real model to measure answer quality.
          </p>
        }
        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                @for (c of columns; track c.key) {
                  <th class="num">{{ c.label }}</th>
                }
              </tr>
            </thead>
            <tbody>
              @for (s of r.strategies | keyvalue: keepOrder; track s.key) {
                <tr>
                  <td>
                    <strong>{{ s.value.title }}</strong>
                    <div class="small muted">{{ s.value.description }}</div>
                  </td>
                  @for (c of columns; track c.key) {
                    <td class="num" [class.best]="isBest(c.key, s.value.overall[c.key])">
                      @if (s.value.overall[c.key] === null) {
                        –
                      } @else if (c.kind === 'pct') {
                        {{ s.value.overall[c.key] | percent: '1.1-1' }}
                      } @else {
                        {{ s.value.overall[c.key] | number: '1.0-1' }}
                      }
                    </td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <h3>Accuracy by question type</h3>
        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                @for (cat of categories(); track cat) {
                  <th class="num">{{ cat }}</th>
                }
              </tr>
            </thead>
            <tbody>
              @for (s of r.strategies | keyvalue: keepOrder; track s.key) {
                <tr>
                  <td>{{ s.value.title }}</td>
                  @for (cat of categories(); track cat) {
                    <td class="num">{{ s.value.by_category[cat]?.accuracy ?? 0 | percent: '1.0-0' }}</td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    } @else if (!error()) {
      <p class="muted">Loading the evaluation report…</p>
    }
  `,
  styles: `
    .scroll { overflow-x: auto; }
    td.best { font-weight: 700; color: var(--ok); }
    .note { background: #fff8e6; border-radius: 6px; padding: 0.5rem 0.75rem; }
    h2, h3 { margin-top: 0; }
  `,
})
export class EvaluationComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly columns = COLUMNS;
  readonly report = signal<EvalReport | null>(null);
  readonly error = signal<string | null>(null);
  readonly categories = computed(() => {
    const r = this.report();
    const cats = new Set<string>();
    Object.values(r?.strategies ?? {}).forEach((s) => Object.keys(s.by_category).forEach((c) => cats.add(c)));
    return [...cats].sort();
  });

  ngOnInit(): void {
    this.api.evalReport().subscribe({
      next: (r) => this.report.set(r),
      error: (e) => this.error.set(errorMessage(e)),
    });
  }

  /** Keep the server's order (naive first) instead of sorting by key. */
  keepOrder(): number {
    return 0;
  }

  isBest(key: MetricKey, value: number | null): boolean {
    if (value === null || key === 'llm_calls' || key === 'tokens') {
      return false;
    }
    const values = Object.values(this.report()?.strategies ?? {})
      .map((s) => s.overall[key])
      .filter((v): v is number => v !== null);
    return values.length > 1 && value === Math.max(...values);
  }
}
