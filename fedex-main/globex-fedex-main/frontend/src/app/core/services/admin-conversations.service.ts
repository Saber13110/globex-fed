import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export interface AdminConversationKpi {
  label: string;
  value: number;
  trend_percent: number;
  trend_up: boolean;
  icon: string;
}

export interface AdminConversationListItem {
  id: number;
  session_id: number;
  title: string;
  preview: string;
  user_id: number;
  user_name: string;
  user_email: string;
  user_status: string;
  user_initial: string;
  category: string;
  status: string;
  status_key: string;
  priority: string;
  is_unread: boolean;
  updated_label: string;
  created_at: string;
}

export interface AdminConversationsPage {
  kpis: AdminConversationKpi[];
  conversations: AdminConversationListItem[];
}

export interface AdminConversationMessage {
  id: number;
  sender: string;
  message_text: string;
  created_at: string;
  time_label: string;
}

export interface AdminConversationAnalytics {
  response_time: string;
  response_time_trend: number;
  resolution_time: string;
  resolution_time_trend: number;
  satisfaction: string;
  satisfaction_trend: number;
  messages: number;
  interactions: number;
}

export interface AdminConversationDetail {
  id: number;
  session_id: number;
  title: string;
  user_id: number;
  user_name: string;
  user_email: string;
  user_status: string;
  user_initial: string;
  category: string;
  status: string;
  status_key: string;
  priority: string;
  channel: string;
  created_at: string;
  created_label: string;
  updated_label: string;
  is_unread: boolean;
  tags: string[];
  messages: AdminConversationMessage[];
  analytics: AdminConversationAnalytics;
}

@Injectable({ providedIn: 'root' })
export class AdminConversationsService {
  constructor(private readonly http: HttpClient) {}

  list(tab = 'all', search = ''): Observable<AdminConversationsPage> {
    let params = new HttpParams().set('tab', tab);
    if (search.trim()) {
      params = params.set('search', search.trim());
    }
    return this.http.get<AdminConversationsPage>(`${API_BASE_URL}/admin/conversations`, { params });
  }

  detail(sessionId: number): Observable<AdminConversationDetail> {
    return this.http.get<AdminConversationDetail>(`${API_BASE_URL}/admin/conversations/${sessionId}`);
  }
}
