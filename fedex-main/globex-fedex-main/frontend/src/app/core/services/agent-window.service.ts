import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { timeout } from 'rxjs/operators';

import { API_BASE_URL } from '../api.config';

export interface AgentWindowHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AgentWindowChatRequest {
  message: string;
  session_id?: string | null;
  conversation_history?: AgentWindowHistoryMessage[];
}

export interface AgentWindowChatResponse {
  reply: string;
  session_id: string;
  jarvis_session_id?: string | null;
  engine?: string;
  latency_ms?: number | null;
  redirect_to_copilot?: boolean;
  copilot_hint?: string | null;
}

export interface AgentWindowSession {
  id: string;
  title: string;
  jarvis_session_id?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface AgentWindowMessage {
  id: number;
  sender: string;
  message_text: string;
  created_at: string;
  latency_ms?: number | null;
}

export interface AgentWindowHealth {
  enabled: boolean;
  online: boolean;
  jarvis_base_url: string;
  detail?: string | null;
  latency_ms?: number | null;
}

@Injectable({ providedIn: 'root' })
export class AgentWindowService {
  private readonly base = `${API_BASE_URL}/admin/agent-window`;

  constructor(private readonly http: HttpClient) {}

  health(): Observable<AgentWindowHealth> {
    return this.http.get<AgentWindowHealth>(`${this.base}/health`).pipe(timeout(8000));
  }

  listSessions(): Observable<{ sessions: AgentWindowSession[] }> {
    return this.http.get<{ sessions: AgentWindowSession[] }>(`${this.base}/sessions`);
  }

  getSession(sessionId: string): Observable<{ session: AgentWindowSession; messages: AgentWindowMessage[] }> {
    return this.http.get<{ session: AgentWindowSession; messages: AgentWindowMessage[] }>(
      `${this.base}/sessions/${sessionId}`,
    );
  }

  deleteSession(sessionId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/sessions/${sessionId}`);
  }

  chat(payload: AgentWindowChatRequest): Observable<AgentWindowChatResponse> {
    return this.http.post<AgentWindowChatResponse>(`${this.base}/chat`, payload).pipe(timeout(130000));
  }
}
