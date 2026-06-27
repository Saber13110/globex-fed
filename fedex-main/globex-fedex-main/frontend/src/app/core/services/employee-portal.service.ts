import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL, AUTH_TOKEN_KEY } from '../api.config';
import { ReportsService } from './reports.service';
import { SupportTicketListResponse, SupportTicketRead } from './support.service';
import { TrackingService } from './tracking.service';

export interface EmployeeDashboardStats {
  open_tickets: number;
  pending_tickets: number;
  total_clients: number;
  unread_notifications: number;
  unread_admin_messages: number;
  recent_trackings: number;
  active_clients: number;
  tracking_exceptions: number;
  pending_escalations: number;
  documents_processed: number;
  pending_actions: number;
  unread_tickets: number;
}

export interface EmployeeHelpdeskMessage {
  id: number;
  author_role: string;
  body: string;
  attachment_url?: string | null;
  created_at: string;
  author_name?: string | null;
  is_internal: boolean;
}

export interface EmployeeHelpdeskTicketSummary {
  id: number;
  ticket_number: string;
  subject: string;
  category: string;
  priority: string;
  status: string;
  customer_name: string;
  customer_email: string;
  client_id: number;
  last_activity: string;
  last_activity_at: string;
  unread: boolean;
  tracking_number: string;
  assigned_employee: string;
  assigned_employee_id: number | null;
  created_at: string;
  updated_at?: string | null;
}

export interface EmployeeHelpdeskTicketListResponse {
  items: EmployeeHelpdeskTicketSummary[];
  total: number;
}

export interface EmployeeHelpdeskTicketDetail {
  id: number;
  ticket_number: string;
  subject: string;
  message: string;
  category: string;
  priority: string;
  status: string;
  attachment_url?: string | null;
  created_at: string;
  updated_at?: string | null;
  customer_name: string;
  customer_email: string;
  client_id: number;
  tracking_number: string;
  assigned_employee: string;
  assigned_employee_id: number | null;
  messages: EmployeeHelpdeskMessage[];
}

export interface EmployeeHelpdeskStats {
  open: number;
  pending: number;
  resolved: number;
  closed: number;
  escalated: number;
  unread: number;
  total_active: number;
}

export interface EmployeeHelpdeskEmployeeOption {
  id: number;
  full_name: string;
  email: string;
}

export interface EmployeeMetricCard {
  key: string;
  value: number;
  label: string;
  trend: string;
  trend_up: boolean;
  icon: string;
}

export interface EmployeeDashboardClientWidget {
  id: number;
  full_name: string;
  company: string;
  email: string;
  last_activity: string;
  avatar_initials: string;
  open_tickets: number;
}

export interface EmployeeDashboardTicketWidget {
  id: number;
  ticket_number: string;
  subject: string;
  priority: string;
  status: string;
  client_name: string;
  created_at: string;
}

export interface EmployeeDashboardTrackingEvent {
  tracking_number: string;
  status: string;
  client_name: string;
  created_at: string;
  is_exception: boolean;
}

export interface EmployeeDashboardTrackingSummary {
  delayed_count: number;
  exception_count: number;
  active_count: number;
  latest_events: EmployeeDashboardTrackingEvent[];
}

export interface EmployeeDashboardAdminComm {
  unread_count: number;
  latest_message: string;
  latest_sender: string;
  latest_at: string | null;
  latest_announcement: string;
}

export interface EmployeeNotification {
  id: number;
  type: string;
  kind: string;
  title: string;
  message: string;
  status: 'read' | 'unread';
  link: string;
  is_read: boolean;
  related_ticket_id?: number | null;
  related_tracking_number?: string;
  related_document_id?: number | null;
  related_client_id?: number | null;
  created_at: string;
  read_at?: string | null;
}

export interface EmployeeNotificationStats {
  all: number;
  unread: number;
  support: number;
  tracking: number;
  documents: number;
  security: number;
}

export interface EmployeeNotificationListResult {
  items: EmployeeNotification[];
  unread_count: number;
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface EmployeeDashboardWorkspace {
  stats: EmployeeDashboardStats;
  metrics: EmployeeMetricCard[];
  recent_clients: EmployeeDashboardClientWidget[];
  recent_tickets: EmployeeDashboardTicketWidget[];
  tracking_summary: EmployeeDashboardTrackingSummary;
  admin_communication: EmployeeDashboardAdminComm;
  recent_notifications: EmployeeNotification[];
}

export interface EmployeeAiClientResult {
  id: number;
  full_name: string;
  email: string;
  company: string;
  open_tickets: number;
  total_trackings: number;
  total_documents: number;
}

export interface EmployeeAiTrackingEvent {
  label: string;
  at: string;
}

export interface EmployeeAiTrackingResult {
  tracking_number: string;
  status: string;
  current_location: string;
  estimated_delivery: string;
  is_exception: boolean;
  client_name: string;
  events: EmployeeAiTrackingEvent[];
}

export interface EmployeeAiTicketResult {
  id: number;
  ticket_number: string;
  subject: string;
  priority: string;
  status: string;
  client_name: string;
}

export interface EmployeeAiDocumentResult {
  id: string;
  title: string;
  doc_type: string;
  created_at: string;
  client_name: string;
  client_id?: number;
  tracking_number?: string;
}

export interface EmployeeAiAction {
  label: string;
  route: string;
  kind: string;
}

export interface EmployeeAiResponse {
  reply: string;
  intent: string;
  context_used: boolean;
  clients: EmployeeAiClientResult[];
  tracking: EmployeeAiTrackingResult | null;
  tickets: EmployeeAiTicketResult[];
  documents: EmployeeAiDocumentResult[];
  admin_draft: string | null;
  actions: EmployeeAiAction[];
}

export interface EmployeeAiAgentCardAction {
  label: string;
  route: string;
}

export interface EmployeeAiAgentCard {
  type: string;
  title: string;
  subtitle: string;
  meta: Record<string, unknown>;
  actions: EmployeeAiAgentCardAction[];
}

export interface EmployeeAiAgentMessageResponse {
  reply: string;
  intent: string;
  conversationId: string;
  cards: EmployeeAiAgentCard[];
  actions: EmployeeAiAction[];
  createdAt?: string;
}

export interface EmployeeAiAgentMessage {
  id: number;
  role: string;
  content: string;
  intent: string;
  cards: EmployeeAiAgentCard[];
  created_at: string;
}

export interface EmployeeAiAgentConversationSummary {
  id: string;
  title: string;
  preview: string;
  group: string;
  created_at: string;
  updated_at: string;
}

export interface EmployeeAiAgentConversationDetail {
  id: string;
  title: string;
  messages: EmployeeAiAgentMessage[];
  created_at: string;
  updated_at: string;
}

export interface EmployeeAiAgentLiveContext {
  recent_clients: EmployeeDashboardClientWidget[];
  recent_shipments: EmployeeDashboardTrackingEvent[];
  recent_tickets: EmployeeDashboardTicketWidget[];
  pending_documents: EmployeeAiDocumentResult[];
  tracking_exceptions: EmployeeDashboardTrackingEvent[];
  unread_notification_count: number;
  unread_admin_count: number;
}

export interface EmployeeChatContextPanel {
  recent_clients: EmployeeDashboardClientWidget[];
  recent_tickets: EmployeeDashboardTicketWidget[];
  tracking_exceptions: EmployeeDashboardTrackingEvent[];
  unread_notifications: EmployeeNotification[];
  admin_messages: EmployeeAdminMessage[];
  unread_admin_count: number;
  unread_notification_count: number;
}

export interface EmployeeSearchHit {
  kind: string;
  id: string;
  title: string;
  subtitle: string;
  link: string;
}

export interface EmployeeClientSummary {
  id: number;
  full_name: string;
  email: string;
  status: string;
  preferred_language: string;
  created_at: string;
  open_tickets: number;
  recent_trackings: number;
  documents_count: number;
  company: string;
  avatar_initials: string;
  last_activity: string;
  pending_issues: number;
  active_shipments: number;
}

export interface EmployeeClientOpsStats {
  total_clients: number;
  active_clients: number;
  open_tickets: number;
  active_shipments: number;
  recent_documents: number;
  pending_issues: number;
  metrics: EmployeeMetricCard[];
}

export interface EmployeeClientActivityEvent {
  id: string;
  kind: string;
  title: string;
  description: string;
  created_at: string;
}

export interface EmployeeClientDetail {
  id: number;
  full_name: string;
  email: string;
  status: string;
  preferred_language: string;
  organization_id: string;
  created_at: string;
  open_tickets: number;
  total_trackings: number;
  total_documents: number;
  company: string;
  avatar_initials: string;
  last_login: string | null;
  last_activity: string;
  pending_issues: number;
  active_shipments: number;
  assigned_employee: string;
  resolved_tickets: number;
}

export interface EmployeeTrackingItem {
  id: number;
  tracking_number: string;
  status: string;
  current_location: string;
  estimated_delivery: string;
  user_question: string;
  created_at: string;
  client_name?: string | null;
  client_id?: number | null;
  status_category?: string;
  is_exception?: boolean;
}

export interface EmployeeShipmentTimelineEvent {
  id: string;
  date: string;
  time: string;
  location: string;
  description: string;
  kind: string;
}

export interface EmployeeShipmentMapPoint {
  label: string;
  lat: number;
  lng: number;
  kind: string;
}

export interface EmployeeShipmentExceptionInfo {
  exception_type: string;
  reason: string;
  priority: string;
  detected_at: string | null;
}

export interface EmployeeShipmentRelatedClient {
  id: number;
  full_name: string;
  email: string;
  avatar_initials: string;
  trackings_count: number;
  tickets_count: number;
  documents_count: number;
}

export interface EmployeeShipmentHealth {
  status: string;
  risk: string;
  exception: boolean;
  pod: boolean;
}

export interface EmployeeShipmentDetail {
  tracking_number: string;
  status: string;
  status_category: string;
  current_location: string;
  recipient: string;
  last_update: string;
  estimated_delivery: string;
  reference_number: string;
  service_type: string;
  weight: string;
  dimensions: string;
  sender: string;
  destination: string;
  client_id: number | null;
  client_name: string;
  client_email: string;
  timeline: EmployeeShipmentTimelineEvent[];
  map_points: EmployeeShipmentMapPoint[];
  exception: EmployeeShipmentExceptionInfo | null;
  pod_available: boolean;
  related_client?: EmployeeShipmentRelatedClient | null;
  health?: EmployeeShipmentHealth | null;
}

export interface EmployeeTrackingOpsStats {
  active_shipments: number;
  delayed_count: number;
  exception_count: number;
  total_trackings: number;
  metrics: EmployeeMetricCard[];
}

export interface EmployeeDocumentItem {
  id: string;
  title: string;
  doc_type: string;
  tracking_number: string;
  client_name: string;
  client_id: number;
  created_at: string;
}

export interface EmployeeAdminMessage {
  id: number;
  sender_role: string;
  sender_name?: string | null;
  body: string;
  attachment_url?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface EmployeeAdminChatParticipant {
  id: string;
  name: string;
  role: string;
  avatar_initial: string;
  online: boolean;
  email?: string;
}

export interface EmployeeAdminChatSharedFile {
  id: number;
  name: string;
  url: string;
  mime_type: string;
  uploaded_at: string;
  uploaded_by: string;
}

export interface EmployeeAdminChatConversation {
  id: string;
  name: string;
  role: string;
  avatar_initial: string;
  online: boolean;
  last_message: string;
  last_message_at: string | null;
  unread_count: number;
}

export interface EmployeeAdminChatWorkspace {
  conversations: EmployeeAdminChatConversation[];
  messages: EmployeeAdminMessage[];
  participants: EmployeeAdminChatParticipant[];
  shared_files: EmployeeAdminChatSharedFile[];
  unread_count: number;
  created_at: string | null;
  last_activity_at: string | null;
}

export interface EmployeeAdminChatSearchHit {
  kind: string;
  id: string;
  title: string;
  subtitle: string;
  message_id?: number | null;
}

export interface EmployeeSettings {
  full_name: string;
  email: string;
  preferred_language: string;
  response_preferences: string;
}

@Injectable({ providedIn: 'root' })
export class EmployeePortalService {
  private readonly base = `${API_BASE_URL}/api/employee`;

  constructor(
    private readonly http: HttpClient,
    private readonly reports: ReportsService,
    private readonly tracking: TrackingService,
  ) {}

  getDashboard(): Observable<EmployeeDashboardWorkspace> {
    return this.http.get<EmployeeDashboardWorkspace>(`${this.base}/dashboard`);
  }

  search(q: string): Observable<{ query: string; items: EmployeeSearchHit[] }> {
    return this.http.get<{ query: string; items: EmployeeSearchHit[] }>(`${this.base}/search`, {
      params: { q },
    });
  }

  listClients(params: Record<string, string> = {}): Observable<{ items: EmployeeClientSummary[]; total: number; page: number; limit: number; total_pages: number }> {
    let hp = new HttpParams();
    for (const [k, v] of Object.entries(params)) {
      if (v) hp = hp.set(k, v);
    }
    return this.http.get<{ items: EmployeeClientSummary[]; total: number; page: number; limit: number; total_pages: number }>(`${this.base}/clients`, { params: hp });
  }

  getClientOpsStats(): Observable<EmployeeClientOpsStats> {
    return this.http.get<EmployeeClientOpsStats>(`${this.base}/clients/stats`);
  }

  getClient(id: number): Observable<EmployeeClientDetail> {
    return this.http.get<EmployeeClientDetail>(`${this.base}/clients/${id}`);
  }

  getClientShipments(id: number): Observable<EmployeeTrackingItem[]> {
    return this.http.get<EmployeeTrackingItem[]>(`${this.base}/clients/${id}/shipments`);
  }

  getClientTrackings(id: number): Observable<EmployeeTrackingItem[]> {
    return this.http.get<EmployeeTrackingItem[]>(`${this.base}/clients/${id}/trackings`);
  }

  private fetchDocumentBlob(doc: EmployeeDocumentItem): Promise<Blob> {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    const url = `${this.base}/documents/${encodeURIComponent(doc.id)}/download`;
    return fetch(url, { headers }).then(async (r) => {
      if (r.ok) return r.blob();
      let message = 'Document unavailable';
      try {
        const body = (await r.json()) as { detail?: string | { msg?: string }[] };
        if (typeof body.detail === 'string') {
          message = body.detail;
        }
      } catch {
        /* ignore parse errors */
      }
      throw new Error(message);
    });
  }

  private documentFilename(doc: EmployeeDocumentItem): string {
    if (doc.id.startsWith('tracking-')) {
      return doc.doc_type === 'proof'
        ? `POD-${doc.tracking_number}.pdf`
        : `shipment-${doc.tracking_number}.pdf`;
    }
    const ext = doc.doc_type === 'export' ? 'xlsx' : 'pdf';
    return `${doc.title}.${ext}`.replace(/[^\w\s.-]/g, '_');
  }

  private triggerBlobDownload(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  downloadClientDocument(
    doc: EmployeeDocumentItem,
    onError?: () => void,
    onSuccess?: () => void,
  ): void {
    void this.fetchDocumentBlob(doc)
      .then((blob) => {
        this.triggerBlobDownload(blob, this.documentFilename(doc));
        onSuccess?.();
      })
      .catch(() => onError?.());
  }

  previewClientDocument(
    doc: EmployeeDocumentItem,
    onError?: () => void,
    onSuccess?: () => void,
  ): void {
    void this.fetchDocumentBlob(doc)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const previewable =
          blob.type === 'application/pdf' ||
          blob.type.startsWith('image/') ||
          /\.pdf$/i.test(doc.title);
        if (previewable) {
          const opened = window.open(url, '_blank', 'noopener,noreferrer');
          if (!opened) {
            this.triggerBlobDownload(blob, this.documentFilename(doc));
          }
          window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
          onSuccess?.();
        } else {
          this.triggerBlobDownload(blob, this.documentFilename(doc));
          onSuccess?.();
        }
      })
      .catch(() => onError?.());
  }

  getClientTickets(id: number): Observable<SupportTicketListResponse> {
    return this.http.get<SupportTicketListResponse>(`${this.base}/clients/${id}/tickets`);
  }

  getClientDocuments(id: number): Observable<EmployeeDocumentItem[]> {
    return this.http.get<EmployeeDocumentItem[]>(`${this.base}/clients/${id}/documents`);
  }

  getClientNotifications(id: number): Observable<{ items: EmployeeNotification[]; unread_count: number }> {
    return this.http.get<{ items: EmployeeNotification[]; unread_count: number }>(
      `${this.base}/clients/${id}/notifications`,
    );
  }

  getClientActivity(id: number): Observable<EmployeeClientActivityEvent[]> {
    return this.http.get<EmployeeClientActivityEvent[]>(`${this.base}/clients/${id}/activity`);
  }

  listShipments(params: Record<string, string> = {}): Observable<{
    items: EmployeeTrackingItem[];
    total: number;
    page: number;
    limit: number;
    total_pages: number;
  }> {
    let hp = new HttpParams();
    for (const [k, v] of Object.entries(params)) {
      if (v) hp = hp.set(k, v);
    }
    return this.http.get<{
      items: EmployeeTrackingItem[];
      total: number;
      page: number;
      limit: number;
      total_pages: number;
    }>(`${this.base}/shipments`, { params: hp });
  }

  searchTracking(q?: string): Observable<EmployeeTrackingItem[]> {
    const params = q ? { q } : undefined;
    return this.http.get<EmployeeTrackingItem[]>(`${this.base}/tracking`, params ? { params } : {});
  }

  getTrackingOpsStats(): Observable<EmployeeTrackingOpsStats> {
    return this.http.get<EmployeeTrackingOpsStats>(`${this.base}/tracking/stats`);
  }

  getShipmentDetail(trackingNumber: string): Observable<EmployeeShipmentDetail> {
    return this.http.get<EmployeeShipmentDetail>(
      `${this.base}/shipments/${encodeURIComponent(trackingNumber)}`,
    );
  }

  exportShipment(trackingNumber: string, format: 'pdf' | 'txt' = 'pdf'): void {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const url = `${this.base}/shipments/${encodeURIComponent(trackingNumber)}/export?format=${format}`;
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (!blob) return;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `shipment-${trackingNumber}.${format}`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  downloadShipmentPod(trackingNumber: string): void {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const url = `${this.base}/shipments/${encodeURIComponent(trackingNumber)}/pod`;
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (!blob) return;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `POD-${trackingNumber}.pdf`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  listDocuments(params: Record<string, string> = {}): Observable<EmployeeDocumentItem[]> {
    let hp = new HttpParams();
    for (const [k, v] of Object.entries(params)) {
      if (v) hp = hp.set(k, v);
    }
    return this.http.get<EmployeeDocumentItem[]>(`${this.base}/documents`, { params: hp });
  }

  listTickets(params: Record<string, string> = {}): Observable<EmployeeHelpdeskTicketListResponse> {
    let hp = new HttpParams();
    for (const [k, v] of Object.entries(params)) {
      if (v) hp = hp.set(k, v);
    }
    return this.http.get<EmployeeHelpdeskTicketListResponse>(`${this.base}/support/tickets`, { params: hp });
  }

  getTicket(id: number): Observable<EmployeeHelpdeskTicketDetail> {
    return this.http.get<EmployeeHelpdeskTicketDetail>(`${this.base}/support/tickets/${id}`);
  }

  getHelpdeskStats(): Observable<EmployeeHelpdeskStats> {
    return this.http.get<EmployeeHelpdeskStats>(`${this.base}/support/helpdesk/stats`);
  }

  listHelpdeskEmployees(): Observable<EmployeeHelpdeskEmployeeOption[]> {
    return this.http.get<EmployeeHelpdeskEmployeeOption[]>(`${this.base}/support/employees`);
  }

  replyTicket(id: number, message: string, attachmentUrl?: string | null): Observable<EmployeeHelpdeskMessage> {
    return this.http.post<EmployeeHelpdeskMessage>(`${this.base}/support/tickets/${id}/reply`, {
      message,
      attachmentUrl: attachmentUrl ?? null,
    });
  }

  addInternalNote(id: number, message: string, attachmentUrl?: string | null): Observable<EmployeeHelpdeskMessage> {
    return this.http.post<EmployeeHelpdeskMessage>(`${this.base}/support/tickets/${id}/internal-note`, {
      message,
      attachmentUrl: attachmentUrl ?? null,
    });
  }

  assignTicket(id: number, employeeId?: number | null): Observable<EmployeeHelpdeskTicketDetail> {
    return this.http.patch<EmployeeHelpdeskTicketDetail>(`${this.base}/support/tickets/${id}/assign`, {
      employee_id: employeeId ?? null,
    });
  }

  updateTicketStatus(id: number, status: string): Observable<SupportTicketRead> {
    return this.http.patch<SupportTicketRead>(`${this.base}/support/tickets/${id}/status`, { status });
  }

  getAdminChatWorkspace(): Observable<EmployeeAdminChatWorkspace> {
    return this.http.get<EmployeeAdminChatWorkspace>(`${this.base}/admin-chat/workspace`);
  }

  searchAdminChat(q: string): Observable<{ query: string; items: EmployeeAdminChatSearchHit[] }> {
    return this.http.get<{ query: string; items: EmployeeAdminChatSearchHit[] }>(`${this.base}/admin-chat/search`, {
      params: new HttpParams().set('q', q),
    });
  }

  sendAdminTyping(active: boolean): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.base}/admin-chat/typing`, { active });
  }

  getAdminChat(): Observable<{ items: EmployeeAdminMessage[]; unread_count: number }> {
    return this.http.get<{ items: EmployeeAdminMessage[]; unread_count: number }>(`${this.base}/admin-chat`);
  }

  sendAdminMessage(body: string, attachmentUrl?: string | null): Observable<EmployeeAdminMessage> {
    return this.http.post<EmployeeAdminMessage>(`${this.base}/admin-chat/messages`, {
      body,
      attachment_url: attachmentUrl ?? null,
    });
  }

  markAdminChatRead(): Observable<{ marked: number }> {
    return this.http.patch<{ marked: number }>(`${this.base}/admin-chat/read`, {});
  }

  getNotificationStats(): Observable<EmployeeNotificationStats> {
    return this.http.get<EmployeeNotificationStats>(`${this.base}/notifications/stats`);
  }

  listNotifications(params: Record<string, string> = {}): Observable<EmployeeNotificationListResult> {
    let hp = new HttpParams();
    for (const [k, v] of Object.entries(params)) {
      if (v) hp = hp.set(k, v);
    }
    return this.http.get<EmployeeNotificationListResult>(`${this.base}/notifications`, { params: hp });
  }

  markNotificationRead(id: number): Observable<EmployeeNotification> {
    return this.http.patch<EmployeeNotification>(`${this.base}/notifications/${id}/read`, {});
  }

  markAllNotificationsRead(): Observable<{ updated: number }> {
    return this.http.patch<{ updated: number }>(`${this.base}/notifications/read-all`, {});
  }

  deleteNotification(id: number): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/notifications/${id}`);
  }

  getSettings(): Observable<EmployeeSettings> {
    return this.http.get<EmployeeSettings>(`${this.base}/settings`);
  }

  updateSettings(payload: Partial<EmployeeSettings>): Observable<EmployeeSettings> {
    return this.http.patch<EmployeeSettings>(`${this.base}/settings`, payload);
  }

  askAi(message: string): Observable<EmployeeAiResponse> {
    return this.http.post<EmployeeAiResponse>(`${this.base}/chat/ai`, { message });
  }

  getChatContext(): Observable<EmployeeChatContextPanel> {
    return this.http.get<EmployeeChatContextPanel>(`${this.base}/chat/context`);
  }

  sendAiAgentMessage(message: string, conversationId?: string | null): Observable<EmployeeAiAgentMessageResponse> {
    return this.http.post<EmployeeAiAgentMessageResponse>(`${this.base}/ai-agent/message`, {
      message,
      conversationId: conversationId ?? null,
    });
  }

  getAiAgentLiveContext(): Observable<EmployeeAiAgentLiveContext> {
    return this.http.get<EmployeeAiAgentLiveContext>(`${this.base}/ai-agent/live-context`);
  }

  listAiAgentConversations(search?: string): Observable<EmployeeAiAgentConversationSummary[]> {
    let params = new HttpParams();
    if (search?.trim()) params = params.set('search', search.trim());
    return this.http.get<EmployeeAiAgentConversationSummary[]>(`${this.base}/ai-agent/conversations`, { params });
  }

  getAiAgentConversation(id: string): Observable<EmployeeAiAgentConversationDetail> {
    return this.http.get<EmployeeAiAgentConversationDetail>(`${this.base}/ai-agent/conversations/${id}`);
  }

  createAiAgentConversation(title = 'New conversation'): Observable<EmployeeAiAgentConversationDetail> {
    return this.http.post<EmployeeAiAgentConversationDetail>(`${this.base}/ai-agent/conversations`, { title });
  }

  updateAiAgentConversation(id: string, title: string): Observable<EmployeeAiAgentConversationSummary> {
    return this.http.patch<EmployeeAiAgentConversationSummary>(`${this.base}/ai-agent/conversations/${id}`, { title });
  }

  deleteAiAgentConversation(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/ai-agent/conversations/${id}`);
  }
}
