import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, of } from 'rxjs';

export type ApiState = 'checking' | 'ready' | 'degraded' | 'down';

export interface ApiStatus {
  state: ApiState;
  detail?: string;
  pgvector?: string;
}

interface ReadyResponse {
  status: string;
  database?: string;
  pgvector?: string;
}

@Injectable({ providedIn: 'root' })
export class HealthService {
  private readonly http = inject(HttpClient);

  /** Asks the API whether it and its database are ready. Never errors. */
  check(): Observable<ApiStatus> {
    return this.http.get<ReadyResponse>('/api/health/ready').pipe(
      map((r): ApiStatus => ({ state: 'ready', pgvector: r.pgvector })),
      catchError((e: HttpErrorResponse) =>
        of<ApiStatus>(
          e.status === 0
            ? { state: 'down', detail: 'API unreachable' }
            : { state: 'degraded', detail: `database ${e.error?.database ?? `HTTP ${e.status}`}` },
        ),
      ),
    );
  }
}
