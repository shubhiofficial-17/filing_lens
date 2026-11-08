import { DecimalPipe, JsonPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { segments } from '../shared/answer-text';
import { Answer } from '../shared/models';

/** One answer: text with clickable citations, the cited excerpts, cost, and the trace. */
@Component({
  selector: 'app-answer-view',
  standalone: true,
  imports: [DecimalPipe, JsonPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="meta small muted">
      <span class="chip">{{ answer().strategy }}</span>
      {{ answer().usage.llm_calls }} model call{{ answer().usage.llm_calls === 1 ? '' : 's' }} ·
      {{ answer().usage.prompt_tokens + answer().usage.completion_tokens | number }} tokens ·
      {{ answer().latency_ms | number: '1.0-0' }} ms · {{ answer().model }}
    </div>
    <p class="answer">
      @for (s of parts(); track $index) {
        @if (s.marker !== null) {
          <button
            type="button"
            class="marker"
            [class.active]="selected() === s.marker"
            (click)="selected.set(s.marker)"
            [attr.aria-label]="'Show source ' + s.marker"
          >
            {{ s.marker }}
          </button>
        } @else {
          <span>{{ s.text }}</span>
        }
      }
    </p>

    @if (answer().citations.length) {
      <h4>Sources</h4>
      <ol class="sources">
        @for (c of answer().citations; track c.marker) {
          <li [class.active]="selected() === c.marker" (click)="selected.set(c.marker)">
            <span class="chip">[{{ c.marker }}] {{ c.ticker }} {{ c.fiscal_year }} · Item {{ c.item }}</span>
            @if (!c.supported) {
              <span class="chip warn">not supported</span>
            }
            <span class="quote">“{{ c.quote }}”</span>
          </li>
        }
      </ol>
    }

    <details>
      <summary class="small">Excerpts the model saw ({{ answer().retrieved.length }})</summary>
      @for (r of answer().retrieved; track r.chunk_id; let i = $index) {
        <div class="excerpt" [class.active]="selected() === i + 1">
          <div class="small muted">
            [{{ i + 1 }}] {{ r.chunk_id }} · {{ r.source }} · score {{ r.score | number: '1.3-3' }}
          </div>
          <pre>{{ r.text }}</pre>
        </div>
      }
    </details>

    <details>
      <summary class="small">Trace ({{ answer().trace.length }} steps)</summary>
      <table class="trace">
        @for (step of answer().trace; track $index) {
          <tr>
            <td>
              <strong>{{ step.name }}</strong>
              @if (step.detail) {
                <span class="muted small"> · {{ step.detail }}</span>
              }
              @if (hasData(step.data)) {
                <pre>{{ step.data | json }}</pre>
              }
            </td>
            <td class="num small">{{ step.ms | number: '1.1-1' }} ms</td>
          </tr>
        }
      </table>
    </details>
  `,
  styles: `
    .answer { font-size: 1.05rem; }
    .marker {
      padding: 0 0.35rem; margin: 0 0.1rem; font-size: 0.75rem; line-height: 1.4;
      vertical-align: super; border-radius: 4px;
    }
    .marker.active, .sources li.active, .excerpt.active { outline: 2px solid var(--accent); }
    .sources { padding-left: 1.2rem; }
    .sources li { margin-bottom: 0.4rem; cursor: pointer; border-radius: 4px; }
    .quote { display: block; color: var(--muted); font-size: 0.9rem; }
    .chip.warn { background: #fdf0e0; color: var(--warn); }
    .excerpt { margin: 0.5rem 0; border-radius: 4px; }
    .trace td { vertical-align: top; }
    details { margin-top: 0.75rem; }
    h4 { margin: 0.75rem 0 0.25rem; }
  `,
})
export class AnswerViewComponent {
  readonly answer = input.required<Answer>();
  readonly selected = signal<number | null>(null);
  readonly parts = computed(() => segments(this.answer().text));

  hasData(data: Record<string, unknown>): boolean {
    return Object.keys(data ?? {}).length > 0;
  }
}
