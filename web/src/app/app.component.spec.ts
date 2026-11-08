import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Observable, of } from 'rxjs';

import { AppComponent } from './app.component';
import { ApiStatus, HealthService } from './health.service';

describe('AppComponent', () => {
  function render(status: ApiStatus): HTMLElement {
    const fake: Pick<HealthService, 'check'> = { check: (): Observable<ApiStatus> => of(status) };
    TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([]), { provide: HealthService, useValue: fake }],
    });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the app name and navigation', () => {
    const el = render({ state: 'ready' });
    expect(el.querySelector('h1')?.textContent).toContain('FilingLens');
    const links = Array.from(el.querySelectorAll('nav a')).map((a) => a.textContent?.trim());
    expect(links).toEqual(['Ask', 'Evaluation', 'Filings']);
  });

  it('shows the API as ready with the pgvector version', () => {
    const el = render({ state: 'ready', pgvector: '0.7.4' });
    const pill = el.querySelector('.pill');
    expect(pill?.textContent).toContain('API ready · pgvector 0.7.4');
    expect(pill?.getAttribute('data-state')).toBe('ready');
  });

  it('shows why the API is not ready', () => {
    const el = render({ state: 'degraded', detail: 'database unreachable' });
    expect(el.querySelector('.pill')?.textContent).toContain('API not ready (database unreachable)');
  });
});
