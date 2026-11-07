import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApiStatus, HealthService } from './health.service';

describe('HealthService', () => {
  let service: HealthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(HealthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  function check(): ApiStatus[] {
    const results: ApiStatus[] = [];
    service.check().subscribe((s) => results.push(s));
    return results;
  }

  it('reports ready with the pgvector version', () => {
    const results = check();
    http.expectOne('/api/health/ready').flush({ status: 'ready', database: 'ok', pgvector: '0.7.4' });
    expect(results).toEqual([{ state: 'ready', pgvector: '0.7.4' }]);
  });

  it('reports degraded with the reason on 503', () => {
    const results = check();
    http
      .expectOne('/api/health/ready')
      .flush({ status: 'unavailable', database: 'unreachable' }, { status: 503, statusText: 'Service Unavailable' });
    expect(results).toEqual([{ state: 'degraded', detail: 'database unreachable' }]);
  });

  it('reports down when the API cannot be reached', () => {
    const results = check();
    http.expectOne('/api/health/ready').error(new ProgressEvent('error'));
    expect(results).toEqual([{ state: 'down', detail: 'API unreachable' }]);
  });
});
