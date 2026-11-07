import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';

import { ApiStatus, HealthService } from './health.service';

@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="top">
      <h1>FilingLens</h1>
      <span class="pill" [attr.data-state]="status().state" role="status">{{ label() }}</span>
    </header>
    <main>
      <p>A research copilot for SEC annual reports.</p>
      <p class="muted">Ingestion, search and agents arrive in the next milestones.</p>
    </main>
  `,
  styles: `
    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem 1.5rem;
      border-bottom: 1px solid var(--border);
      background: #fff;
    }
    h1 {
      margin: 0;
      font-size: 1.25rem;
    }
    main {
      padding: 1.5rem;
    }
    .muted {
      color: var(--muted);
    }
    .pill {
      font-size: 0.8rem;
      padding: 0.2rem 0.6rem;
      border-radius: 999px;
      border: 1px solid currentColor;
      color: var(--muted);
    }
    .pill[data-state='ready'] {
      color: var(--ok);
    }
    .pill[data-state='degraded'] {
      color: var(--warn);
    }
    .pill[data-state='down'] {
      color: var(--bad);
    }
  `,
})
export class AppComponent implements OnInit {
  private readonly health = inject(HealthService);

  readonly status = signal<ApiStatus>({ state: 'checking' });

  readonly label = computed(() => {
    const s = this.status();
    switch (s.state) {
      case 'checking':
        return 'Checking API…';
      case 'ready':
        return s.pgvector ? `API ready · pgvector ${s.pgvector}` : 'API ready';
      case 'degraded':
        return `API not ready (${s.detail})`;
      case 'down':
        return 'API unreachable';
    }
  });

  ngOnInit(): void {
    this.health.check().subscribe((s) => this.status.set(s));
  }
}
