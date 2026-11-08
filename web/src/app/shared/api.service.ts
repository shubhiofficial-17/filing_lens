import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  Answer,
  AskRequest,
  EvalReport,
  Filing,
  FilingDetail,
  Section,
  Strategy,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  strategies(): Observable<Strategy[]> {
    return this.http.get<Strategy[]>('/api/strategies');
  }

  ask(body: AskRequest): Observable<Answer> {
    return this.http.post<Answer>('/api/ask', body);
  }

  filings(): Observable<Filing[]> {
    return this.http.get<Filing[]>('/api/filings');
  }

  filing(id: string): Observable<FilingDetail> {
    return this.http.get<FilingDetail>(`/api/filings/${encodeURIComponent(id)}`);
  }

  section(id: string): Observable<Section> {
    return this.http.get<Section>(`/api/sections/${encodeURIComponent(id)}`);
  }

  ingest(ticker: string, limit: number): Observable<{ ingested: { id: string; sections: number }[] }> {
    return this.http.post<{ ingested: { id: string; sections: number }[] }>('/api/filings/ingest', {
      source: 'edgar',
      ticker,
      limit,
    });
  }

  evalReport(): Observable<EvalReport> {
    return this.http.get<EvalReport>('/api/eval/report');
  }
}

/** Server problem details ({detail: ...}) or a generic message. */
export function errorMessage(e: unknown): string {
  const err = e as { status?: number; error?: { detail?: unknown } };
  if (err?.status === 0) {
    return 'The API is unreachable.';
  }
  const detail = err?.error?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: { msg?: string }) => d.msg ?? 'invalid input').join('; ');
  }
  return `Request failed (${err?.status ?? 'unknown error'}).`;
}
