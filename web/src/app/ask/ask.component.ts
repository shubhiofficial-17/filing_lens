import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { catchError, concatMap, from, of, tap } from 'rxjs';

import { ApiService, errorMessage } from '../shared/api.service';
import { Answer, Strategy } from '../shared/models';
import { AnswerViewComponent } from './answer-view.component';

interface Run {
  strategy: string;
  title: string;
  answer: Answer | null;
  error: string | null;
}

export const EXAMPLES = [
  'Who was the CFO of Northwind Robotics in fiscal 2025?',
  'Which company owns Helix Vision Ltd., and who was that company’s CEO in fiscal 2025?',
  'How did Northwind Robotics’ revenue change between fiscal 2023 and fiscal 2025?',
  'Compare the fiscal 2024 revenue of Bluefin Health and Solace Energy.',
  'Summarise Solace Energy’s fiscal 2025 revenue results.',
];

@Component({
  selector: 'app-ask',
  standalone: true,
  imports: [FormsModule, AnswerViewComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="panel">
      <form (ngSubmit)="ask()">
        <label for="question" class="small muted">Ask about the 10-K filings</label>
        <textarea
          id="question"
          name="question"
          rows="2"
          [(ngModel)]="question"
          maxlength="500"
          placeholder="e.g. Who was Bluefin Health's CEO in fiscal 2025?"
        ></textarea>
        <div class="row">
          <select name="strategy" [(ngModel)]="strategy" aria-label="Strategy">
            @for (s of strategies(); track s.name) {
              <option [value]="s.name">{{ s.title }}</option>
            }
          </select>
          <button type="submit" [disabled]="busy() || question.trim().length < 3">Ask</button>
          <button
            type="button"
            class="secondary"
            (click)="compareAll()"
            [disabled]="busy() || question.trim().length < 3"
          >
            Compare all strategies
          </button>
          @if (busy()) {
            <span class="muted small">Working…</span>
          }
        </div>
        @if (description()) {
          <p class="small muted">{{ description() }}</p>
        }
      </form>
      <div class="examples small">
        <span class="muted">Try:</span>
        @for (e of examples; track e) {
          <button type="button" class="link" (click)="useExample(e)">{{ e }}</button>
        }
      </div>
    </section>

    @if (error()) {
      <p class="error" role="alert">{{ error() }}</p>
    }

    <div class="runs" [class.grid]="runs().length > 1">
      @for (run of runs(); track run.strategy) {
        <article class="panel" [attr.data-strategy]="run.strategy">
          <h3>{{ run.title }}</h3>
          @if (run.answer) {
            <app-answer-view [answer]="run.answer" />
          } @else if (run.error) {
            <p class="error">{{ run.error }}</p>
          } @else {
            <p class="muted small">Waiting…</p>
          }
        </article>
      }
    </div>
  `,
  styles: `
    textarea { width: 100%; resize: vertical; margin: 0.25rem 0 0.5rem; }
    .row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    .examples { margin-top: 0.75rem; display: flex; flex-wrap: wrap; gap: 0.25rem 0.75rem; }
    button.link {
      background: none; border: none; color: var(--accent); padding: 0; text-align: left;
      text-decoration: underline;
    }
    .runs.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 1rem; }
    h3 { margin: 0 0 0.25rem; }
  `,
})
export class AskComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly examples = EXAMPLES;
  readonly strategies = signal<Strategy[]>([]);
  readonly runs = signal<Run[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  question = '';
  strategy = 'routed';

  ngOnInit(): void {
    this.api.strategies().subscribe({
      next: (list) => {
        this.strategies.set(list);
        if (!list.some((s) => s.name === this.strategy) && list.length) {
          this.strategy = list[0].name;
        }
      },
      error: (e) => this.error.set(errorMessage(e)),
    });
  }

  description(): string {
    return this.strategies().find((s) => s.name === this.strategy)?.description ?? '';
  }

  useExample(text: string): void {
    this.question = text;
  }

  ask(): void {
    this.run([this.strategy]);
  }

  compareAll(): void {
    this.run(this.strategies().map((s) => s.name));
  }

  private run(names: string[]): void {
    const question = this.question.trim();
    if (question.length < 3 || !names.length) {
      return;
    }
    const titles = new Map(this.strategies().map((s) => [s.name, s.title]));
    this.error.set(null);
    this.busy.set(true);
    this.runs.set(names.map((n) => ({ strategy: n, title: titles.get(n) ?? n, answer: null, error: null })));

    // One at a time: the strategies share the model endpoint and its rate limits.
    from(names)
      .pipe(
        concatMap((name) =>
          this.api.ask({ question, strategy: name }).pipe(
            tap((answer) => this.update(name, { answer })),
            catchError((e) => {
              this.update(name, { error: errorMessage(e) });
              return of(null);
            }),
          ),
        ),
      )
      .subscribe({ complete: () => this.busy.set(false) });
  }

  private update(name: string, patch: Partial<Run>): void {
    this.runs.update((runs) => runs.map((r) => (r.strategy === name ? { ...r, ...patch } : r)));
  }
}
