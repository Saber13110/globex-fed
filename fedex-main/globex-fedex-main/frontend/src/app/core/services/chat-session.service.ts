import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export interface ChatSessionSummary {
  id: number;
  title: string;
  collection_id: number | null;
  tags: string;
  is_pinned: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatCollection {
  id: number;
  name: string;
  created_at: string;
}

export interface ChatSessionMessage {
  id: number;
  sender: 'user' | 'bot' | 'system';
  source: 'fedex_api' | 'llm' | 'export' | 'fallback' | 'unknown' | 'user_input';
  message_text: string;
  created_at: string;
}

export interface ShareConversationResponse {
  share_token: string;
  include_tracking_details: boolean;
}

export interface ImportSharedConversationResponse {
  session_id: number;
}

@Injectable({ providedIn: 'root' })
export class ChatSessionService {
  constructor(private readonly http: HttpClient) {}

  list(params: {
    limit?: number;
    search?: string;
    collection_id?: number;
    smart_view?: string;
    include_archived?: boolean;
  } = {}): Observable<ChatSessionSummary[]> {
    const query: Record<string, string | number | boolean> = {
      limit: params.limit ?? 100,
    };
    if (params.search) query['search'] = params.search;
    if (typeof params.collection_id === 'number') query['collection_id'] = params.collection_id;
    if (params.smart_view) query['smart_view'] = params.smart_view;
    if (typeof params.include_archived === 'boolean') query['include_archived'] = params.include_archived;

    return this.http.get<ChatSessionSummary[]>(`${API_BASE_URL}/chat/sessions`, {
      params: query as never,
    });
  }

  listMessages(sessionId: number): Observable<ChatSessionMessage[]> {
    return this.http.get<ChatSessionMessage[]>(`${API_BASE_URL}/chat/sessions/${sessionId}/messages`);
  }

  update(
    sessionId: number,
    payload: { title?: string; is_pinned?: boolean; is_archived?: boolean; collection_id?: number; tags?: string },
  ): Observable<ChatSessionSummary> {
    return this.http.patch<ChatSessionSummary>(`${API_BASE_URL}/chat/sessions/${sessionId}`, payload);
  }

  delete(sessionId: number): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/chat/sessions/${sessionId}`);
  }

  listCollections(): Observable<ChatCollection[]> {
    return this.http.get<ChatCollection[]>(`${API_BASE_URL}/chat/collections`);
  }

  createCollection(name: string): Observable<ChatCollection> {
    return this.http.post<ChatCollection>(`${API_BASE_URL}/chat/collections`, { name });
  }

  createShareLink(sessionId: number, include_tracking_details = false): Observable<ShareConversationResponse> {
    return this.http.post<ShareConversationResponse>(`${API_BASE_URL}/chat/sessions/${sessionId}/share`, {
      include_tracking_details,
    });
  }

  importSharedConversation(shareToken: string): Observable<ImportSharedConversationResponse> {
    return this.http.post<ImportSharedConversationResponse>(`${API_BASE_URL}/chat/shared/${shareToken}/import`, {});
  }
}
