import { HttpClient } from '@angular/common/http';
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export type UserNotificationType =
  | 'support_message'
  | 'admin_reply'
  | 'tracking_update'
  | 'document_ready'
  | 'export_ready'
  | 'system_alert'
  | 'ai_report'
  | 'security_alert';

export interface UserNotification {
  id: number;
  user_id: number;
  sender_id: number | null;
  sender_role: string | null;
  type: UserNotificationType | string;
  title: string;
  message: string;
  status: 'unread' | 'read';
  priority: 'low' | 'medium' | 'high' | string;
  related_ticket_id: number | null;
  related_tracking_number: string;
  link: string;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}

export interface UserNotificationListResponse {
  items: UserNotification[];
  unread_count: number;
  total: number;
}

@Injectable({ providedIn: 'root' })
export class UserNotificationsService implements OnDestroy {
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
    if (this.pollTimer) {
      return;
    }
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

  list(params?: {
    type?: string;
    status?: string;
    q?: string;
    limit?: number;
  }): Observable<UserNotificationListResponse> {
    const q = new URLSearchParams();
    if (params?.type) q.set('type', params.type);
    if (params?.status) q.set('status', params.status);
    if (params?.q) q.set('q', params.q);
    if (params?.limit != null) q.set('limit', String(params.limit));
    const qs = q.toString();
    return this.http.get<UserNotificationListResponse>(
      `${API_BASE_URL}/api/notifications/me${qs ? `?${qs}` : ''}`,
    );
  }

  getUnreadCount(): Observable<{ count: number }> {
    return this.http.get<{ count: number }>(`${API_BASE_URL}/api/notifications/me/unread-count`);
  }

  markRead(id: number): Observable<UserNotification> {
    return this.http.patch<UserNotification>(`${API_BASE_URL}/api/notifications/${id}/read`, {});
  }

  markAllRead(): Observable<{ updated: number }> {
    return this.http.patch<{ updated: number }>(`${API_BASE_URL}/api/notifications/read-all`, {});
  }

  delete(id: number): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${API_BASE_URL}/api/notifications/${id}`);
  }

  private triggerFreshPulse(): void {
    this.freshPulseSubject.next(true);
    if (this.pulseTimer) {
      clearTimeout(this.pulseTimer);
    }
    this.pulseTimer = setTimeout(() => {
      this.freshPulseSubject.next(false);
      this.pulseTimer = null;
    }, 4500);
  }
}
