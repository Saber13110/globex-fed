import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL, AUTH_TOKEN_KEY } from '../api.config';

export interface ReportKpiItem {
  key: string;
  label: string;
  value: number;
  display_value: string;
  trend_percent: number;
  trend_up: boolean;
  sparkline: number[];
}

export interface ChartPoint {
  name: string;
  value: number;
}

export interface ReportCatalogItem {
  slug: string;
  name: string;
  description: string;
  category: string;
  default_format: string;
  period: string;
  last_run_id: number | null;
  last_status: string | null;
  last_created_at: string | null;
  generated_by_name: string | null;
}

export interface ReportRun {
  id: number;
  slug: string;
  name: string;
  category: string;
  format: string;
  period_label: string;
  status: string;
  file_size: number;
  row_count: number;
  generated_by_name: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ReportSchedule {
  id: number;
  name: string;
  slug: string;
  frequency: string;
  run_time: string;
  recipients: string;
  format: string;
  active: boolean;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class ReportsService {
  constructor(private readonly http: HttpClient) {}

  getKpis(dateFrom?: string, dateTo?: string): Observable<{ items: ReportKpiItem[] }> {
    const q = this.qs({ date_from: dateFrom, date_to: dateTo });
    return this.http.get<{ items: ReportKpiItem[] }>(`${API_BASE_URL}/api/reports/kpis${q}`);
  }

  getCharts(dateFrom?: string, dateTo?: string): Observable<{
    shipments_trend: ChartPoint[];
    delivery_performance: ChartPoint[];
    delayed_shipments: ChartPoint[];
    country_statistics: ChartPoint[];
  }> {
    const q = this.qs({ date_from: dateFrom, date_to: dateTo });
    return this.http.get<{
      shipments_trend: ChartPoint[];
      delivery_performance: ChartPoint[];
      delayed_shipments: ChartPoint[];
      country_statistics: ChartPoint[];
    }>(`${API_BASE_URL}/api/reports/charts${q}`);
  }

  listReports(params: Record<string, string | number>): Observable<{
    items: ReportCatalogItem[];
    runs: ReportRun[];
    total: number;
    page: number;
    page_size: number;
  }> {
    const q = this.qs(params);
    return this.http.get<{
      items: ReportCatalogItem[];
      runs: ReportRun[];
      total: number;
      page: number;
      page_size: number;
    }>(`${API_BASE_URL}/api/reports${q}`);
  }

  generate(slug: string, format: string, dateFrom?: string, dateTo?: string): Observable<{ run: ReportRun; download_url: string }> {
    return this.http.post<{ run: ReportRun; download_url: string }>(`${API_BASE_URL}/api/reports/generate`, {
      slug,
      format,
      date_from: dateFrom,
      date_to: dateTo,
    });
  }

  getSchedules(): Observable<ReportSchedule[]> {
    return this.http.get<ReportSchedule[]>(`${API_BASE_URL}/api/reports/schedules`);
  }

  createSchedule(payload: Partial<ReportSchedule>): Observable<ReportSchedule> {
    return this.http.post<ReportSchedule>(`${API_BASE_URL}/api/reports/schedules`, payload);
  }

  getRecent(): Observable<{ items: ReportRun[] }> {
    return this.http.get<{ items: ReportRun[] }>(`${API_BASE_URL}/api/reports/runs/recent`);
  }

  aiReport(prompt: string): Observable<{
    reply: string;
    suggested_slug?: string;
    run?: ReportRun;
    download_url?: string;
  }> {
    return this.http.post<{
      reply: string;
      suggested_slug?: string;
      run?: ReportRun;
      download_url?: string;
    }>(`${API_BASE_URL}/api/ai/reports`, { prompt });
  }

  deleteRun(id: number): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/api/reports/runs/${id}`);
  }

  shareRun(id: number): Observable<{ share_url: string; message: string }> {
    return this.http.post<{ share_url: string; message: string }>(`${API_BASE_URL}/api/reports/runs/${id}/share`, {});
  }

  previewRun(id: number): Observable<{ columns: string[]; rows: string[][]; total_rows: number }> {
    return this.http.get<{ columns: string[]; rows: string[][]; total_rows: number }>(
      `${API_BASE_URL}/api/reports/runs/${id}/preview`,
    );
  }

  downloadRun(id: number, filename: string): void {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const url = `${API_BASE_URL}/api/reports/runs/${id}/download`;
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => {
        if (!r.ok) throw new Error('download failed');
        return r.blob();
      })
      .then((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  exportFormat(format: 'excel' | 'csv' | 'json' | 'pdf', slug: string, dateFrom?: string, dateTo?: string): void {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const path = format === 'excel' ? 'excel' : format;
    const q = this.qs({ slug, date_from: dateFrom, date_to: dateTo });
    const url = `${API_BASE_URL}/api/reports/export/${path}${q}`;
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => {
        if (!r.ok) throw new Error('export failed');
        return r.blob();
      })
      .then((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${slug}.${format === 'excel' ? 'xlsx' : format}`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  private qs(params: Record<string, string | number | undefined | null>): string {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v != null && v !== '') q.set(k, String(v));
    }
    const s = q.toString();
    return s ? `?${s}` : '';
  }
}
