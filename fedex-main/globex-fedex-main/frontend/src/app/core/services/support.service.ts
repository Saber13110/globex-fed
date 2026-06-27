import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { map } from 'rxjs/operators';

import { API_BASE_URL } from '../api.config';

export interface FaqItem {
  id: string;
  question: string;
  answer: string;
}

export interface FaqListResponse {
  items: FaqItem[];
  language: string;
}

export interface SupportTicketCreate {
  subject: string;
  message: string;
  category?: string;
  priority?: string;
  attachmentUrl?: string | null;
}

export interface SupportTicketCreated {
  success: boolean;
  ticketId: string;
  id: number;
  status: string;
  createdAt: string;
}

export interface SupportTicketMessage {
  id: number;
  author_role: 'user' | 'admin' | string;
  body: string;
  attachment_url?: string | null;
  created_at: string;
  author_name?: string | null;
}

export interface SupportTicketRead {
  id: number;
  ticket_number?: string;
  subject: string;
  message: string;
  category?: string;
  priority?: string;
  status: string;
  attachment_url?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface SupportTicketDetail extends SupportTicketRead {
  messages: SupportTicketMessage[];
}

export interface SupportTicketListResponse {
  items: SupportTicketRead[];
}

export interface ClientNotification {
  id: number;
  kind: string;
  title: string;
  message: string;
  link: string;
  reference_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface ClientNotificationListResponse {
  items: ClientNotification[];
  unread_count: number;
}

export interface SupportAttachmentUploadResponse {
  url: string;
  filename: string;
}

export const SUPPORT_ATTACHMENT_MAX_BYTES = 15 * 1024 * 1024;

const BLOCKED_SUPPORT_EXTENSIONS = new Set([
  '.exe', '.bat', '.cmd', '.com', '.msi', '.scr', '.ps1', '.sh', '.dll', '.vbs', '.js', '.jar',
]);

@Injectable({ providedIn: 'root' })
export class SupportService {
  constructor(private readonly http: HttpClient) {}

  getFaq(lang?: string): Observable<FaqListResponse> {
    const q = lang ? `?lang=${encodeURIComponent(lang)}` : '';
    return this.http.get<FaqListResponse>(`${API_BASE_URL}/support/faq${q}`);
  }

  listTickets(): Observable<SupportTicketListResponse> {
    return this.http.get<SupportTicketListResponse>(`${API_BASE_URL}/api/support/tickets/me`);
  }

  getTicket(id: number): Observable<SupportTicketDetail> {
    return this.http.get<SupportTicketDetail>(`${API_BASE_URL}/api/support/tickets/${id}`);
  }

  createTicket(payload: SupportTicketCreate): Observable<SupportTicketCreated> {
    return this.http.post<SupportTicketCreated>(`${API_BASE_URL}/api/support/tickets`, {
      subject: payload.subject,
      message: payload.message,
      category: payload.category ?? 'other',
      priority: payload.priority ?? 'medium',
      attachmentUrl: payload.attachmentUrl ?? null,
    });
  }

  addMessage(ticketId: number, message: string, attachmentUrl?: string | null): Observable<SupportTicketMessage> {
    return this.http.post<SupportTicketMessage>(`${API_BASE_URL}/api/support/tickets/${ticketId}/messages`, {
      message,
      attachmentUrl: attachmentUrl ?? null,
    });
  }

  listNotifications(): Observable<ClientNotificationListResponse> {
    return this.http.get<ClientNotificationListResponse>(`${API_BASE_URL}/api/support/notifications`);
  }

  getUnreadCount(): Observable<{ count: number }> {
    return this.http.get<{ count: number }>(`${API_BASE_URL}/api/notifications/me/unread-count`);
  }

  markNotificationRead(id: number): Observable<ClientNotification> {
    return this.http.patch<ClientNotification>(`${API_BASE_URL}/api/notifications/${id}/read`, {});
  }

  uploadAttachment(file: File): Observable<SupportAttachmentUploadResponse> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<SupportAttachmentUploadResponse>(`${API_BASE_URL}/api/support/attachments`, form);
  }

  resolveAttachmentUrl(url: string | null | undefined): string {
    if (!url) {
      return '';
    }
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return url;
    }
    const base = API_BASE_URL.replace(/\/$/, '');
    return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`;
  }

  attachmentDisplayName(url: string | null | undefined): string {
    if (!url) {
      return 'attachment';
    }
    try {
      const clean = url.split('?')[0];
      const raw = decodeURIComponent(clean.split('/').pop() || 'attachment');
      const parts = raw.split('_');
      return parts.length > 1 ? parts.slice(1).join('_') : raw;
    } catch {
      return 'attachment';
    }
  }

  /** Télécharge ou ouvre une pièce jointe avec le token JWT (évite « Not authenticated »). */
  openAttachment(url: string | null | undefined, filename?: string): Observable<void> {
    const resolved = this.resolveAttachmentUrl(url);
    if (!resolved) {
      return throwError(() => new Error('missing attachment url'));
    }
    const name = filename || this.attachmentDisplayName(url);
    return this.http.get(resolved, { responseType: 'blob' }).pipe(
      map((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        const previewable =
          blob.type.startsWith('image/') ||
          blob.type === 'application/pdf' ||
          /\.(pdf|png|jpe?g|gif|webp)$/i.test(name);
        if (previewable) {
          window.open(blobUrl, '_blank', 'noopener,noreferrer');
          window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
        } else {
          const anchor = document.createElement('a');
          anchor.href = blobUrl;
          anchor.download = name;
          anchor.click();
          URL.revokeObjectURL(blobUrl);
        }
      }),
    );
  }

  validateAttachmentFile(file: File): string | null {
    const ext = file.name.includes('.') ? `.${file.name.split('.').pop()!.toLowerCase()}` : '';
    if (BLOCKED_SUPPORT_EXTENSIONS.has(ext)) {
      return 'type';
    }
    if (file.size > SUPPORT_ATTACHMENT_MAX_BYTES) {
      return 'size';
    }
    return null;
  }
}
