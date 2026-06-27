import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export interface AdminUser {
  id: number;
  full_name: string;
  email: string;
  role: string;
  status: string;
  organization_id: string;
  preferred_language: string;
  created_at: string;
  last_activity_at?: string | null;
  is_online?: boolean;
  last_location?: string | null;
  messages_count?: number;
  trackings_count?: number;
}

export interface ActivityLogEntry {
  id: number;
  user_id: number | null;
  actor_user_id: number | null;
  user_email: string | null;
  user_name: string | null;
  actor_email: string | null;
  level: string;
  category: string;
  action: string;
  message: string;
  metadata_json: string;
  ip_address: string;
  created_at: string;
}

export interface ActivityLogListResponse {
  items: ActivityLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface QuotaLimits {
  messages_per_day: number | null;
  trackings_per_day: number | null;
  exports_per_day: number | null;
}

export interface QuotaUsage {
  messages_today: number;
  trackings_today: number;
  exports_today: number;
}

export interface UserQuotaStatus {
  limits: QuotaLimits;
  usage: QuotaUsage;
  remaining: QuotaLimits;
  exempt: boolean;
}

export interface UserSessionRead {
  id: number;
  browser: string;
  machine: string;
  location: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminUserDetail {
  id: number;
  full_name: string;
  email: string;
  role: string;
  status: string;
  preferred_language: string;
  response_preferences: string;
  organization_id: string;
  created_at: string;
  sessions_count: number;
  messages_count: number;
  trackings_count: number;
  last_activity_at?: string | null;
  is_online?: boolean;
  last_location?: string | null;
  recent_sessions?: UserSessionRead[];
  quotas?: UserQuotaStatus | null;
}

export interface PreferenceProfileStructured {
  tone: string;
  cite_fedex: boolean;
  short_answers: boolean;
  free_notes: string;
}

export interface PreferenceSubmission {
  id: number;
  user_id: number;
  user_email: string | null;
  user_name: string | null;
  proposed_text: string;
  structured?: PreferenceProfileStructured | null;
  status: string;
  risk_score: number;
  risk_reasons: string[];
  rejection_note: string;
  created_at: string;
  reviewed_at: string | null;
}

export interface AdminUserUpdatePayload {
  full_name?: string;
  role?: string;
  status?: string;
  preferred_language?: string;
  response_preferences?: string;
  /** 0 = illimité, >0 = plafond journalier */
  quota_messages_per_day?: number;
  quota_trackings_per_day?: number;
  quota_exports_per_day?: number;
}

export type AdminNotificationKind = 'employee_pending' | 'preference_pending' | 'support_ticket';

export interface AdminNotification {
  id: string;
  kind: AdminNotificationKind;
  reference_id: number;
  user_name: string | null;
  user_email: string | null;
  risk_score: number | null;
  created_at: string;
}

export interface AdminNotificationsResponse {
  items: AdminNotification[];
  total: number;
}

export interface AdminDashboardStats {
  total_users: number;
  total_clients: number;
  total_employees: number;
  total_admins: number;
  total_sessions: number;
  total_messages: number;
  total_tracking_requests: number;
  pending_employees: number;
  messages_last_7_days: number;
  trackings_last_7_days: number;
  new_users_last_7_days: number;
  sessions_last_7_days: number;
  logs_last_7_days: number;
  total_events?: number;
  events_today?: number;
  pending_preference_submissions: number;
  email_configured: boolean;
  fedex_enabled: boolean;
  llm_enabled: boolean;
}

export interface AdminSupportTicketMessage {
  id: number;
  author_role: string;
  body: string;
  attachment_url?: string | null;
  created_at: string;
  author_name?: string | null;
}

export interface AdminSupportTicketSummary {
  id: number;
  ticket_number?: string | null;
  subject: string;
  message: string;
  category?: string;
  priority?: string;
  status: string;
  created_at: string;
  updated_at?: string | null;
}

export interface AdminSupportTicketDetail extends AdminSupportTicketSummary {
  messages: AdminSupportTicketMessage[];
  user_name?: string | null;
  user_email?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminService {
  constructor(private readonly http: HttpClient) {}

  getDashboard(): Observable<AdminDashboardStats> {
    return this.http.get<AdminDashboardStats>(`${API_BASE_URL}/admin/dashboard`);
  }

  getNotifications(limit = 30): Observable<AdminNotificationsResponse> {
    return this.http.get<AdminNotificationsResponse>(`${API_BASE_URL}/admin/notifications`, {
      params: { limit: String(limit) },
    });
  }

  listLogs(params: {
    user_id?: number;
    category?: string;
    level?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }): Observable<ActivityLogListResponse> {
    const q = new URLSearchParams();
    if (params.user_id != null) q.set('user_id', String(params.user_id));
    if (params.category) q.set('category', params.category);
    if (params.level) q.set('level', params.level);
    if (params.q) q.set('q', params.q);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return this.http.get<ActivityLogListResponse>(`${API_BASE_URL}/admin/logs${qs ? `?${qs}` : ''}`);
  }

  getUserDetail(id: number): Observable<AdminUserDetail> {
    return this.http.get<AdminUserDetail>(`${API_BASE_URL}/admin/users/${id}`);
  }

  updateUser(id: number, payload: AdminUserUpdatePayload): Observable<AdminUserDetail> {
    return this.http.patch<AdminUserDetail>(`${API_BASE_URL}/admin/users/${id}`, payload);
  }

  suspendUser(userId: number, reason = ''): Observable<{ suspended: boolean; user_id: number }> {
    return this.http.post<{ suspended: boolean; user_id: number }>(
      `${API_BASE_URL}/admin/users/${userId}/suspend`,
      { reason },
    );
  }

  reactivateUser(userId: number): Observable<{ reactivated: boolean; user_id: number }> {
    return this.http.post<{ reactivated: boolean; user_id: number }>(
      `${API_BASE_URL}/admin/users/${userId}/reactivate`,
      {},
    );
  }

  deleteUser(id: number): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/admin/users/${id}`);
  }

  listPendingPreferences(): Observable<PreferenceSubmission[]> {
    return this.http.get<PreferenceSubmission[]>(`${API_BASE_URL}/admin/preferences/pending`);
  }

  approvePreference(id: number): Observable<PreferenceSubmission> {
    return this.http.post<PreferenceSubmission>(`${API_BASE_URL}/admin/preferences/${id}/approve`, {});
  }

  rejectPreference(id: number, note?: string): Observable<PreferenceSubmission> {
    return this.http.post<PreferenceSubmission>(`${API_BASE_URL}/admin/preferences/${id}/reject`, {
      note: note ?? null,
    });
  }

  sendTestEmail(to: string): Observable<{ sent: boolean }> {
    return this.http.post<{ sent: boolean }>(`${API_BASE_URL}/admin/test-email`, { to });
  }

  listUsers(): Observable<AdminUser[]> {
    return this.http.get<AdminUser[]>(`${API_BASE_URL}/admin/users`);
  }

  inviteUser(payload: {
    full_name: string;
    email: string;
    role: string;
    preferred_language?: string;
  }): Observable<{ user: AdminUser; email_sent: boolean; message: string }> {
    return this.http.post<{ user: AdminUser; email_sent: boolean; message: string }>(
      `${API_BASE_URL}/admin/users/invite`,
      payload,
    );
  }

  listPendingEmployees(): Observable<AdminUser[]> {
    return this.http.get<AdminUser[]>(`${API_BASE_URL}/admin/employees/pending`);
  }

  validateEmployee(id: number): Observable<AdminUser> {
    return this.http.post<AdminUser>(`${API_BASE_URL}/admin/employees/${id}/validate`, {});
  }

  resetEmployeePassword(id: number): Observable<AdminUser> {
    return this.http.post<AdminUser>(`${API_BASE_URL}/admin/employees/${id}/reset-password`, {});
  }

  rejectEmployee(id: number): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/admin/employees/${id}`);
  }

  listSupportTickets(status = 'all'): Observable<{ items: AdminSupportTicketSummary[] }> {
    return this.http.get<{ items: AdminSupportTicketSummary[] }>(
      `${API_BASE_URL}/api/admin/support/tickets?status=${encodeURIComponent(status)}`,
    );
  }

  getSupportTicket(id: number): Observable<AdminSupportTicketDetail> {
    return this.http.get<AdminSupportTicketDetail>(`${API_BASE_URL}/api/admin/support/tickets/${id}`);
  }

  replySupportTicket(id: number, message: string, attachmentUrl?: string | null): Observable<AdminSupportTicketMessage> {
    return this.http.post<AdminSupportTicketMessage>(`${API_BASE_URL}/api/admin/support/tickets/${id}/reply`, {
      message,
      attachmentUrl: attachmentUrl ?? null,
    });
  }

  updateSupportTicketStatus(id: number, status: string): Observable<AdminSupportTicketSummary> {
    return this.http.patch<AdminSupportTicketSummary>(`${API_BASE_URL}/api/admin/support/tickets/${id}/status`, {
      status,
    });
  }

  closeSupportTicket(id: number): Observable<AdminSupportTicketSummary> {
    return this.http.patch<AdminSupportTicketSummary>(`${API_BASE_URL}/api/admin/support/tickets/${id}/close`, {});
  }

  listEmployeeChats(q?: string): Observable<AdminEmployeeChatListItem[]> {
    const params = q ? { q } : undefined;
    return this.http.get<AdminEmployeeChatListItem[]>(`${API_BASE_URL}/api/admin/employee-chat`, { params });
  }

  getEmployeeChatMessages(employeeId: number): Observable<AdminEmployeeChatMessages> {
    return this.http.get<AdminEmployeeChatMessages>(
      `${API_BASE_URL}/api/admin/employee-chat/${employeeId}/messages`,
    );
  }

  sendEmployeeChatMessage(
    employeeId: number,
    body: string,
    attachmentUrl?: string | null,
  ): Observable<AdminEmployeeChatMessage> {
    return this.http.post<AdminEmployeeChatMessage>(
      `${API_BASE_URL}/api/admin/employee-chat/${employeeId}/messages`,
      { body, attachment_url: attachmentUrl ?? null },
    );
  }

  listSecurityIncidents(status = 'open', limit = 50, offset = 0): Observable<SecurityIncidentListResponse> {
    return this.http.get<SecurityIncidentListResponse>(`${API_BASE_URL}/admin/security/incidents`, {
      params: { status, limit, offset },
    });
  }

  resolveSecurityIncident(id: number, status: string, note?: string): Observable<SecurityIncident> {
    return this.http.patch<SecurityIncident>(`${API_BASE_URL}/admin/security/incidents/${id}`, {
      status,
      note: note ?? null,
    });
  }

  suspendUserFromIncident(id: number): Observable<{ suspended: boolean; user_id: number }> {
    return this.http.post<{ suspended: boolean; user_id: number }>(
      `${API_BASE_URL}/admin/security/incidents/${id}/suspend-user`,
      {},
    );
  }

  getSecurityPolicy(): Observable<SecurityPolicy> {
    return this.http.get<SecurityPolicy>(`${API_BASE_URL}/admin/security/policy`);
  }

  updateSecurityPolicy(payload: Partial<SecurityPolicyUpdate>): Observable<SecurityPolicy> {
    return this.http.patch<SecurityPolicy>(`${API_BASE_URL}/admin/security/policy`, payload);
  }

  triggerIdsScan(includeAi = true): Observable<{ rules_incidents: number; ai_incidents: number }> {
    return this.http.post<{ rules_incidents: number; ai_incidents: number }>(
      `${API_BASE_URL}/admin/security/scan`,
      {},
      { params: { include_ai: includeAi } },
    );
  }

  reactivateSecurityUser(userId: number): Observable<{ reactivated: boolean; user_id: number }> {
    return this.reactivateUser(userId);
  }

  askSecurityAgent(message: string): Observable<SecurityAgentResponse> {
    return this.http.post<SecurityAgentResponse>(`${API_BASE_URL}/admin/security/agent`, { message });
  }
}

export interface AdminEmployeeChatListItem {
  id: number;
  full_name: string;
  email: string;
  avatar_initial: string;
  unread_count: number;
  last_message: string;
  last_message_at: string | null;
}

export interface AdminEmployeeChatMessage {
  id: number;
  sender_role: string;
  sender_name: string | null;
  body: string;
  attachment_url: string | null;
  is_read: boolean;
  created_at: string;
}

export interface AdminEmployeeChatMessages {
  items: AdminEmployeeChatMessage[];
  unread_count: number;
}

export interface SecurityIncident {
  id: number;
  user_id: number | null;
  user_name: string | null;
  user_email: string | null;
  user_status: string | null;
  ip_address: string;
  source: string;
  threat_type: string;
  severity: string;
  score: number;
  status: string;
  title: string;
  summary: string;
  evidence: Record<string, unknown>;
  recommended_action: string;
  auto_eligible: boolean;
  created_at: string;
  resolved_at: string | null;
  resolution_note: string;
}

export interface SecurityIncidentListResponse {
  items: SecurityIncident[];
  total: number;
  open_count: number;
}

export interface SecurityPolicyRule {
  trigger: string;
  threshold: number;
  action: string;
}

export interface SecurityPolicy {
  auto_mode_enabled: boolean;
  ai_ids_enabled: boolean;
  rules: SecurityPolicyRule[];
  enabled_by_admin_id: number | null;
  enabled_at: string | null;
  updated_at: string | null;
}

export interface SecurityPolicyUpdate {
  auto_mode_enabled?: boolean;
  ai_ids_enabled?: boolean;
  rules?: SecurityPolicyRule[];
}

export interface SecurityAgentResponse {
  reply: string;
  actions_taken: string[];
  auto_mode_enabled: boolean;
}
