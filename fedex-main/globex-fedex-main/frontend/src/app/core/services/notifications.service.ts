import { HttpClient } from '@angular/common/http';
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

import { API_BASE_URL, AUTH_TOKEN_KEY } from '../api.config';

export interface NotificationKpiItem {
  key: string;
  label: string;
  value: number;
  trend_value: number;
  trend_up: boolean;
  trend_label: string;
  icon: string;
  sparkline: number[];
}

export interface NotificationItem {
  id: number;
  category: string;
  title: string;
  message: string;
  tracking_number: string;
  route: string;
  priority: string;
  channel: string;
  icon: string;
  action_label: string;
  action_type: string;
  action_ref: string;
  is_read: boolean;
  is_archived: boolean;
  created_at: string;
  time_label: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
  unread_count: number;
}

export interface NotificationPreferences {
  web_enabled: boolean;
  email_enabled: boolean;
  sms_enabled: boolean;
  ai_reports: boolean;
  incidents: boolean;
}

export interface AiNotificationInsight {
  id: string;
  text: string;
  tone: string;
}

export interface TimelineEvent {
  id: string;
  time_label: string;
  title: string;
  subtitle: string;
  icon: string;
  tone: string;
  created_at: string;
}

export interface NotificationOverview {
  stats: { kpis: NotificationKpiItem[]; unread_count: number };
  ai_insights: AiNotificationInsight[];
  timeline: TimelineEvent[];
}

export type NotificationTab = 'all' | 'colis' | 'ia' | 'users' | 'system' | 'incidents';

@Injectable({ providedIn: 'root' })
export class NotificationsService implements OnDestroy {
  private readonly unreadSubject = new BehaviorSubject<number>(0);
  private readonly freshPulseSubject = new BehaviorSubject<boolean>(false);
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private pollConsumers = 0;
  private pulseTimer: ReturnType<typeof setTimeout> | null = null;

  readonly unread$ = this.unreadSubject.asObservable();
  readonly freshPulse$ = this.freshPulseSubject.asObservable();

  constructor(private readonly http: HttpClient) {}

  ngOnDestroy(): void {
    this.stopPolling(true);
  }

  get unreadCount(): number {
    return this.unreadSubject.value;
  }

  startPolling(intervalMs = 12_000): void {
    this.pollConsumers += 1;
    if (this.pollTimer) return;
    this.refreshUnread();
    this.pollTimer = setInterval(() => this.refreshUnread(), intervalMs);
  }

  stopPolling(force = false): void {
    if (force) {
      this.pollConsumers = 0;
    } else {
      this.pollConsumers = Math.max(0, this.pollConsumers - 1);
    }
    if (this.pollConsumers === 0 && this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  refreshUnread(): void {
    this.getUnreadCount().subscribe({
      next: ({ count }) => {
        const prev = this.unreadSubject.value;
        this.unreadSubject.next(count);
        if (count > prev) {
          this.triggerFreshPulse();
        }
      },
      error: () => {},
    });
  }

  setUnreadCount(count: number): void {
    this.unreadSubject.next(count);
  }

  private triggerFreshPulse(): void {
    this.freshPulseSubject.next(true);
    if (this.pulseTimer) clearTimeout(this.pulseTimer);
    this.pulseTimer = setTimeout(() => {
      this.freshPulseSubject.next(false);
      this.pulseTimer = null;
    }, 4500);
  }

  getOverview(): Observable<NotificationOverview> {
    return this.http.get<NotificationOverview>(`${API_BASE_URL}/api/admin/notifications/overview`);
  }

  list(params: {
    tab?: string;
    search?: string;
    sort?: string;
    status?: string;
    priority?: string;
    channel?: string;
    page?: number;
    page_size?: number;
  }): Observable<NotificationListResponse> {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
    });
    const qs = q.toString();
    return this.http.get<NotificationListResponse>(`${API_BASE_URL}/api/admin/notifications${qs ? `?${qs}` : ''}`);
  }

  getUnreadCount(): Observable<{ count: number }> {
    return this.http.get<{ count: number }>(`${API_BASE_URL}/api/admin/notifications/unread-count`);
  }

  markRead(id: number, read = true): Observable<NotificationItem> {
    return this.http.patch<NotificationItem>(`${API_BASE_URL}/api/admin/notifications/${id}/read?read=${read}`, {});
  }

  markAllRead(): Observable<{ updated: number }> {
    return this.http.patch<{ updated: number }>(`${API_BASE_URL}/api/admin/notifications/read-all`, {});
  }

  delete(id: number): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${API_BASE_URL}/api/admin/notifications/${id}`);
  }

  archive(id: number): Observable<NotificationItem> {
    return this.http.post<NotificationItem>(`${API_BASE_URL}/api/admin/notifications/${id}/archive`, {});
  }

  getPreferences(): Observable<NotificationPreferences> {
    return this.http.get<NotificationPreferences>(`${API_BASE_URL}/api/admin/notifications/preferences`);
  }

  savePreferences(prefs: Partial<NotificationPreferences>): Observable<NotificationPreferences> {
    return this.http.patch<NotificationPreferences>(`${API_BASE_URL}/api/admin/notifications/preferences`, prefs);
  }

  exportHistory(format: 'csv' | 'xlsx'): void {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const url = `${API_BASE_URL}/api/admin/notifications/export?format=${format}`;
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = format === 'xlsx' ? 'notifications.xlsx' : 'notifications.csv';
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  testAlert(title?: string, message?: string): Observable<NotificationItem> {
    return this.http.post<NotificationItem>(`${API_BASE_URL}/api/admin/notifications/test-alert`, { title, message });
  }

  createRule(name: string, category = 'system', channel = 'web'): Observable<NotificationItem> {
    return this.http.post<NotificationItem>(`${API_BASE_URL}/api/admin/notifications/rules`, { name, category, channel });
  }

  importWebhooks(): Observable<{ imported: number; message: string }> {
    return this.http.post<{ imported: number; message: string }>(`${API_BASE_URL}/api/fedex/webhooks/import`, {});
  }

  generateAiReport(): Observable<{ reply: string; report_id: number | null }> {
    return this.http.post<{ reply: string; report_id: number | null }>(`${API_BASE_URL}/api/admin/notifications/ai-report`, {});
  }

  streamUrl(): string {
    return `${API_BASE_URL}/api/admin/notifications/stream`;
  }
}
