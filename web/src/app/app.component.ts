import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ApiStatus, HealthService } from './health.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="top">
      <div class="brand">
        <h1>FilingLens</h1>
        <span class="muted small">Research copilot for SEC 10-K filings</span>
      </div>
      <nav>
        <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Ask</a>
        <a routerLink="/evaluation" routerLinkActive="active">Evaluation</a>
        <a routerLink="/filings" routerLinkActive="active">Filings</a>
      </nav>
      <span class="pill" [attr.data-state]="status().state" role="status">{{ label() }}</span>
    </header>
    <main>
      <router-outlet />
    </main>
  `,
  styles: `
    .top {
      display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;
      padding: 0.75rem 1.5rem; border-bottom: 1px solid var(--border); background: #fff;
    }
    .brand { display: flex; align-items: baseline; gap: 0.75rem; }
    h1 { margin: 0; font-size: 1.25rem; }
    nav { display: flex; gap: 1rem; flex: 1; }
    nav a { text-decoration: none; color: var(--muted); padding: 0.2rem 0; }
    nav a.active { color: var(--fg); border-bottom: 2px solid var(--accent); }
    main { padding: 1.25rem 1.5rem; max-width: 1400px; margin: 0 auto; }
    .pill {
      font-size: 0.8rem; padding: 0.2rem 0.6rem; border-radius: 999px;
      border: 1px solid currentColor; color: var(--muted);
    }
    .pill[data-state='ready'] { color: var(--ok); }
    .pill[data-state='degraded'] { color: var(--warn); }
    .pill[data-state='down'] { color: var(--bad); }
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
