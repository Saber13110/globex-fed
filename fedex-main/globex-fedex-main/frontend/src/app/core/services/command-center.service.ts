import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export interface HeroStatItem {
  label: string;
  value: number;
  icon: string;
}

export interface OverviewMetric {
  label: string;
  value: string;
  trend_percent: number;
  trend_up: boolean;
  icon: string;
}

export interface ExecutiveInsight {
  id: string;
  tone: string;
  message: string;
  icon: string;
}

export interface KpiCardData {
  title: string;
  value: number;
  trend_percent: number;
  trend_up: boolean;
  sparkline: number[];
  icon?: string;
  display_value?: string | null;
  suffix?: string;
}

export interface LiveShipmentItem {
  id: number;
  route: string;
  origin: string;
  destination: string;
  origin_flag: string;
  destination_flag: string;
  carrier: string;
  tracking_number: string;
  status: string;
  status_key: string;
  eta_label: string;
  progress_percent: number;
  updated_at: string;
}

export interface RecentConversationItem {
  id: number;
  session_id: number;
  title: string;
  preview: string;
  user_name: string | null;
  priority: string;
  created_at: string;
}

export interface SystemHealthItem {
  name: string;
  key: string;
  status: string;
  percent: number;
  operational: boolean;
}

export interface UserRoleSlice {
  label: string;
  role_key: string;
  count: number;
  color: string;
}

export interface RecentUserItem {
  id: number;
  full_name: string;
  email: string;
  role: string;
  created_at: string;
}

export interface FedexApiMetrics {
  requests_today: number;
  success_rate: number;
  latency_ms: number;
  error_rate: number;
  requests_series: { label: string; value: number }[];
}

export interface ActivityTimelineItem {
  time_label: string;
  message: string;
  category: string;
  level: string;
  created_at: string;
}

export interface CommandCenterPayload {
  hero_stats: HeroStatItem[];
  today_overview: OverviewMetric[];
  executive_insights: ExecutiveInsight[];
  kpis: KpiCardData[];
  live_shipments: LiveShipmentItem[];
  recent_conversations: RecentConversationItem[];
  system_health: SystemHealthItem[];
  user_roles: UserRoleSlice[];
  pending_invitations: number;
  recent_users: RecentUserItem[];
  fedex_metrics: FedexApiMetrics;
  activity_timeline: ActivityTimelineItem[];
  open_incidents: number;
  notification_count: number;
  total_users: number;
  online_users?: number;
  generated_at?: string | null;
}

export interface CommandCenterAiResponse {
  reply: string;
  intent?: string | null;
}

export type DashboardRoleFilter = 'all' | 'client' | 'employe' | 'admin';

export interface DashboardNavEvent {
  target: string;
  trackingNumber?: string;
  shipmentId?: number;
  conversationId?: number;
  roleKey?: DashboardRoleFilter;
  healthKey?: string;
  auditQuery?: string;
}

@Injectable({ providedIn: 'root' })
export class CommandCenterService {
  constructor(private readonly http: HttpClient) {}

  getPayload(): Observable<CommandCenterPayload> {
    return this.http.get<CommandCenterPayload>(`${API_BASE_URL}/admin/command-center`);
  }

  askAi(message: string, quickAction?: string): Observable<CommandCenterAiResponse> {
    return this.http.post<CommandCenterAiResponse>(`${API_BASE_URL}/admin/command-center/ai`, {
      message,
      quick_action: quickAction ?? null,
    });
  }
}
