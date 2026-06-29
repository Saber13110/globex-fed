import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { timeout } from 'rxjs/operators';

import { API_BASE_URL } from '../api.config';
import { AdminExportDownloadSpec } from './admin-ai.service';
import { ShipmentSummary } from './chatbot.service';

export interface JarvisHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface JarvisAgentStep {
  label: string;
  status: string;
  detail?: string | null;
}

export interface JarvisChatRequest {
  message: string;
  agent_mode?: boolean;
  conversation_history?: JarvisHistoryMessage[];
  ui_language?: string;
  chat_session_id?: number | null;
  image_base64?: string | null;
  image_mime_type?: string | null;
  file_name?: string | null;
}

export interface JarvisChatResponse {
  reply: string;
  mode?: string;
  tools_used?: string[];
  agent_steps?: JarvisAgentStep[];
  needs_approval?: boolean;
  approval_id?: number | null;
  approval_hint?: string | null;
  mission_id?: number | null;
  action_executed?: boolean;
  export_download?: AdminExportDownloadSpec | null;
  llm_degraded?: boolean;
  intent?: string | null;
  execution_time_ms?: number | null;
  shipment?: ShipmentSummary | null;
  chat_session_id?: number | null;
}

export interface JarvisHealthResponse {
  enabled: boolean;
  ollama_model: string;
  ollama_online: boolean;
  ollama_tags_ok?: boolean;
  ollama_inference_ok?: boolean;
  detail?: string | null;
  kernel_version?: string;
}

export interface JarvisApprovalResponse {
  approval_id: number;
  status: string;
  reply?: string | null;
  mission_id?: number | null;
}

@Injectable({ providedIn: 'root' })
export class JarvisAdminService {
  private readonly base = `${API_BASE_URL}/api/globex-agent`;

  constructor(private readonly http: HttpClient) {}

  health(): Observable<JarvisHealthResponse> {
    return this.http.get<JarvisHealthResponse>(`${this.base}/health`).pipe(timeout(25000));
  }

  chat(payload: JarvisChatRequest): Observable<JarvisChatResponse> {
    return this.http.post<JarvisChatResponse>(`${this.base}/chat`, payload).pipe(timeout(310000));
  }

  approve(approvalId: number): Observable<JarvisApprovalResponse> {
    return this.http
      .post<JarvisApprovalResponse>(`${this.base}/approve/${approvalId}`, {})
      .pipe(timeout(310000));
  }

  reject(approvalId: number): Observable<JarvisApprovalResponse> {
    return this.http
      .post<JarvisApprovalResponse>(`${this.base}/reject/${approvalId}`, {})
      .pipe(timeout(60000));
  }
}
