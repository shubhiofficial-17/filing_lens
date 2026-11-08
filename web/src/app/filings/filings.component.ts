import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, errorMessage } from '../shared/api.service';
import { Filing, FilingDetail, Section } from '../shared/models';

@Component({
  selector: 'app-filings',
  standalone: true,
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="layout">
      <aside class="panel">
        <h3>Filings</h3>
        <ul class="list">
          @for (f of filings(); track f.id) {
            <li>
              <button type="button" class="item" [class.active]="detail()?.id === f.id" (click)="open(f.id)">
                <strong>{{ f.ticker }}</strong> fiscal {{ f.fiscal_year }}
                <span class="small muted">{{ f.company }}</span>
              </button>
            </li>
          } @empty {
            <li class="muted small">No filings yet.</li>
          }
        </ul>
        <form class="ingest" (ngSubmit)="ingest()">
          <label for="ticker" class="small muted">Add 10-Ks from SEC EDGAR</label>
          <div class="row">
            <input id="ticker" name="ticker" [(ngModel)]="ticker" placeholder="Ticker, e.g. MSFT" maxlength="10" />
            <button type="submit" [disabled]="busy() || !ticker.trim()">Ingest</button>
          </div>
          @if (message()) {
            <p class="small" [class.error]="failed()">{{ message() }}</p>
          }
        </form>
      </aside>

      <section class="panel content">
        @if (detail(); as d) {
          <h2>{{ d.company }} · fiscal {{ d.fiscal_year }}</h2>
          <p class="small muted">
            {{ d.form }} filed {{ d.filed_on }} · CIK {{ d.cik }} ·
            @if (d.source_url.startsWith('http')) {
              <a [href]="d.source_url" target="_blank" rel="noopener">source on EDGAR</a>
            } @else {
              fixture (fictional company)
            }
          </p>
          <div class="tabs">
            @for (s of d.sections; track s.id) {
              <button
                type="button"
                class="secondary"
                [class.active]="section()?.id === s.id"
                (click)="openSection(s.id)"
              >
                Item {{ s.item }} · {{ s.title }}
              </button>
            }
          </div>
          @if (section(); as s) {
            <h3>Item {{ s.item }}. {{ s.title }}</h3>
            <pre class="text">{{ s.text }}</pre>
          }
        } @else {
          <p class="muted">Pick a filing to read its sections.</p>
        }
        @if (error()) {
          <p class="error" role="alert">{{ error() }}</p>
        }
      </section>
    </div>
  `,
  styles: `
    .layout { display: grid; grid-template-columns: 280px 1fr; gap: 1rem; }
    @media (max-width: 800px) { .layout { grid-template-columns: 1fr; } }
    .list { list-style: none; padding: 0; margin: 0 0 1rem; }
    button.item {
      width: 100%; text-align: left; background: none; color: var(--fg); border: none;
      padding: 0.35rem 0.5rem; border-radius: 6px; display: flex; flex-direction: column;
    }
    button.item.active, .tabs button.active { background: var(--accent-soft); }
    .tabs { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .row { display: flex; gap: 0.4rem; }
    .row input { flex: 1; min-width: 0; }
    .text { font-size: 0.9rem; background: none; padding: 0; }
    h2, h3 { margin-top: 0; }
  `,
})
export class FilingsComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly filings = signal<Filing[]>([]);
  readonly detail = signal<FilingDetail | null>(null);
  readonly section = signal<Section | null>(null);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);
  readonly message = signal<string | null>(null);
  readonly failed = signal(false);
  ticker = '';

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.filings().subscribe({
      next: (f) => this.filings.set(f),
      error: (e) => this.error.set(errorMessage(e)),
    });
  }

  open(id: string): void {
    this.section.set(null);
    this.api.filing(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        if (d.sections.length) {
          this.openSection(d.sections[0].id);
        }
      },
      error: (e) => this.error.set(errorMessage(e)),
    });
  }

  openSection(id: string): void {
    this.api.section(id).subscribe({
      next: (s) => this.section.set(s),
      error: (e) => this.error.set(errorMessage(e)),
    });
  }

  ingest(): void {
    const ticker = this.ticker.trim();
    this.busy.set(true);
    this.message.set(`Downloading ${ticker.toUpperCase()} from EDGAR…`);
    this.failed.set(false);
    this.api.ingest(ticker, 3).subscribe({
      next: (r) => {
        this.message.set(`Added ${r.ingested.map((i) => i.id).join(', ')}.`);
        this.busy.set(false);
        this.load();
      },
      error: (e) => {
        this.message.set(errorMessage(e));
        this.failed.set(true);
        this.busy.set(false);
      },
    });
  }
}
