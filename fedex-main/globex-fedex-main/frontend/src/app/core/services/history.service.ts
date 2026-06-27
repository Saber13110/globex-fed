import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { API_BASE_URL } from '../api.config';
import { ExportDownloadSpec } from './chatbot.service';

export interface HistoryItem {
  id: number;
  session_id: number | null;
  tracking_number: string;
  user_question: string;
  bot_response: string;
  status: string | null;
  current_location: string | null;
  estimated_delivery: string | null;
  created_at: string;
}

export type ExportLang = 'fr' | 'en' | 'ar';

@Injectable({ providedIn: 'root' })
export class HistoryService {
  constructor(private readonly http: HttpClient) {}

  list(limit = 50): Observable<HistoryItem[]> {
    return this.http.get<HistoryItem[]>(`${API_BASE_URL}/history`, { params: { limit } });
  }

  isPdfExport(spec?: ExportDownloadSpec | string | null): boolean {
    if (spec != null && typeof spec === 'object') {
      const fmt = (spec.format ?? '').toLowerCase();
      if (fmt === 'pdf') {
        return true;
      }
      if (fmt === 'xlsx' || fmt === 'excel') {
        return false;
      }
      const p = (spec.preset ?? '').toLowerCase();
      return (
        p === 'tracking' ||
        p === 'tracking_summary' ||
        p === 'text_pdf' ||
        p.includes('pdf')
      );
    }
    const p = (typeof spec === 'string' ? spec : '').toLowerCase();
    return p === 'tracking_summary' || p === 'text_pdf' || p.includes('pdf');
  }

  exportFilename(spec?: ExportDownloadSpec | null, preset?: string | null): string {
    if (spec?.filename) {
      return spec.filename;
    }
    const p = (preset ?? spec?.preset ?? '').toLowerCase();
    if (this.isPdfExport(spec ?? preset)) {
      if (p === 'tracking_summary') {
        return 'rapport-suivis-jour.pdf';
      }
      if (p === 'text_pdf') {
        return 'document.pdf';
      }
      return 'historique-suivi.pdf';
    }
    return 'tracking-export.xlsx';
  }

  downloadFromSpec(spec: ExportDownloadSpec, lang: ExportLang = 'fr'): Observable<Blob> {
    if (spec.export_token) {
      return this.downloadTextPdf({
        exportToken: spec.export_token,
        filename: spec.filename ?? undefined,
      });
    }
    const limit = Math.max(spec.tracking_numbers?.length ?? 0, 1, 100);
    const common = {
      lang,
      sessionId: spec.session_id,
      trackingNumbers: spec.tracking_numbers,
      includeEvents: spec.include_events ?? true,
      limit,
      preset: spec.preset,
    };
    if (this.isPdfExport(spec)) {
      return this.downloadPdf(common);
    }
    return this.downloadExcel({ ...common, preset: 'tracking' });
  }

  downloadExcel(options?: {
    limit?: number;
    lang?: ExportLang;
    columns?: string[];
    preset?: string;
    sessionId?: number;
    trackingNumbers?: string[];
    includeEvents?: boolean;
  }): Observable<Blob> {
    const limit = options?.limit ?? 100;
    const lang = options?.lang ?? 'fr';
    const columns = options?.columns?.length ? options.columns.join(',') : undefined;
    const includeEvents = options?.includeEvents ?? false;
    const preset = options?.preset;
    const sessionId = options?.sessionId;
    const trackingNumbers = options?.trackingNumbers?.length
      ? options.trackingNumbers.join(',')
      : undefined;
    return this.http
      .get(`${API_BASE_URL}/export/tracking-history.xlsx`, {
        params: {
          limit,
          lang,
          include_events: includeEvents,
          ...(columns ? { columns } : {}),
          ...(preset ? { preset } : {}),
          ...(sessionId ? { session_id: sessionId } : {}),
          ...(trackingNumbers ? { tracking_numbers: trackingNumbers } : {}),
        },
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          this.triggerDownload(
            blob,
            preset === 'tracking' ? 'tracking-export.xlsx' : 'tracking-history.xlsx',
          );
        }),
      );
  }

  downloadPdf(options?: {
    limit?: number;
    lang?: ExportLang;
    preset?: string;
    sessionId?: number;
    trackingNumbers?: string[];
    includeEvents?: boolean;
  }): Observable<Blob> {
    const limit = options?.limit ?? 100;
    const lang = options?.lang ?? 'fr';
    const includeEvents = options?.includeEvents ?? true;
    const preset = options?.preset;
    const sessionId = options?.sessionId;
    const trackingNumbers = options?.trackingNumbers?.length
      ? options.trackingNumbers.join(',')
      : undefined;
    const filename =
      preset === 'tracking_summary' ? 'rapport-suivis-jour.pdf' : 'historique-suivi.pdf';
    return this.http
      .get(`${API_BASE_URL}/export/tracking-history.pdf`, {
        params: {
          limit,
          lang,
          include_events: includeEvents,
          ...(preset ? { preset } : {}),
          ...(sessionId ? { session_id: sessionId } : {}),
          ...(trackingNumbers ? { tracking_numbers: trackingNumbers } : {}),
        },
        responseType: 'blob',
      })
      .pipe(tap((blob) => this.triggerDownload(blob, filename)));
  }

  downloadTextPdf(options: { exportToken: string; filename?: string }): Observable<Blob> {
    const filename = options.filename ?? 'document.pdf';
    return this.http
      .get(`${API_BASE_URL}/export/text.pdf`, {
        params: { export_token: options.exportToken },
        responseType: 'blob',
      })
      .pipe(tap((blob) => this.triggerDownload(blob, filename)));
  }

  private triggerDownload(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }
}
