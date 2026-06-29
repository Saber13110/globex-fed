import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, tap, timeout, catchError, throwError } from 'rxjs';

import { API_BASE_URL } from '../api.config';
import { AgentQuestionnaire } from '../models/chat-send.model';

export interface AiAssistantKpi {
  key: string;
  label: string;
  value: string;
  trend_percent: number;
  trend_up: boolean;
  icon: string;
}

export interface AiInsightItem {
  id: string;
  title: string;
  description: string;
  tone: string;
  badge: string;
  icon: string;
}

export interface AiCapabilityItem {
  key: string;
  title: string;
  description: string;
  icon: string;
}

export interface AiServiceStatus {
  key: string;
  name: string;
  status: string;
  operational: boolean;
}

export interface AiDataSource {
  key: string;
  name: string;
  connected: boolean;
  detail: string;
}

export interface AiSuggestionItem {
  id: string;
  text: string;
  action: string;
}

export interface AiConversationItem {
  id: number;
  question: string;
  created_at: string;
  status: string;
  source: string;
  session_id?: number | null;
}

export interface AiAssistantOverview {
  kpis: AiAssistantKpi[];
  insights: AiInsightItem[];
  capabilities: AiCapabilityItem[];
  system_status: AiServiceStatus[];
  data_sources: AiDataSource[];
  smart_suggestions: AiSuggestionItem[];
  ask_examples: string[];
  recent_conversations: AiConversationItem[];
  quick_commands: string[];
}

export interface AgentStep {
  label: string;
  status: string;
  detail?: string | null;
}

export interface AgentReasoning {
  objective?: string;
  plan?: string[];
  action_tool?: string;
  action_label?: string;
  verification?: string;
  verified?: boolean | null;
  verification_note?: string;
}

export interface AdminExportDownloadSpec {
  preset: string;
  hours?: number;
  limit?: number;
  module?: string;
  /** Copilot admin : chaîne ; pipeline client : parfois tableau. */
  tracking_numbers?: string | string[];
  filename: string;
  format?: 'pdf' | 'xlsx';
  export_token?: string;
  records?: number;
  /** Champs renvoyés par le pipeline admin_client (exports client). */
  session_id?: number;
  include_events?: boolean;
}

export interface CopilotState {
  last_module?: string | null;
  last_intent?: string | null;
  last_query_type?: string | null;
  last_tool_used?: string | null;
  last_items?: Record<string, unknown>[];
  last_payload?: Record<string, unknown> | null;
  last_result_summary?: string | null;
  last_exportable_result?: boolean;
  last_limit?: number | null;
  last_format?: string | null;
  last_entity_ids?: number[];
  last_tracking_numbers?: string[];
  last_user_ids?: number[];
  last_notification_ids?: number[];
  last_report_context?: Record<string, unknown> | null;
}

export interface CopilotHistoryMessage {
  role: 'user' | 'assistant' | 'admin' | 'agent';
  content: string;
}

export interface CopilotAttachmentDisplay {
  name: string;
  kind: 'image' | 'pdf' | 'excel' | 'word' | 'text' | 'other';
  previewUrl?: string;
  mimeType?: string;
}

export interface ExportPreviewPayload {
  intent_id: string;
  module: string;
  format: string;
  records: number;
  period: string;
  estimated_size_kb: number;
  filename: string;
  hours?: number;
  limit?: number;
}

export interface ExportExecuteResponse {
  success: boolean;
  file_name?: string | null;
  download_url?: string | null;
  records?: number;
  export_download?: AdminExportDownloadSpec | null;
  export_status?: 'pending' | 'in_progress' | 'completed' | 'error';
  error?: string | null;
  reply?: string | null;
}

export interface CopilotChatMessage {
  id: number;
  role: 'admin' | 'agent';
  content: string;
  createdAt: Date;
  attachment?: CopilotAttachmentDisplay | null;
  agentTypeLabel?: string;
  analysisOnly?: boolean;
  agentSteps?: AgentStep[];
  agentReasoning?: AgentReasoning | null;
  actionExecuted?: boolean;
  needsApproval?: boolean;
  approvalId?: number | null;
  missionId?: number | null;
  exportDownload?: AdminExportDownloadSpec | null;
  agentQuestionnaire?: AgentQuestionnaire | null;
  llmDegraded?: boolean;
  llmProvider?: string | null;
  gptSlug?: string | null;
  knowledgeHits?: number;
  toolsUsed?: string[];
  mode?: 'gemini' | 'gemini_pro' | 'ollama' | 'local_fallback' | string | null;
  confidence?: number | null;
  reasoningSummary?: string | null;
  error?: string | null;
  language?: string | null;
  executionTimeMs?: number | null;
  sourcesUsed?: AiSourceUsed[];
  requiresConfirmation?: boolean;
  suggestedAction?: Record<string, unknown> | null;
  exportPreview?: ExportPreviewPayload | null;
  exportStatus?: 'pending' | 'in_progress' | 'completed' | 'error' | null;
  exportProgressStep?: number;
  exportResult?: ExportExecuteResponse | null;
}

export interface AiAssistantQueryResponse {
  reply: string;
  intent?: string | null;
  conversation_id?: number | null;
  agent_type?: string | null;
  agent_type_label?: string | null;
  mission_id?: number | null;
  action_executed?: boolean;
  needs_approval?: boolean;
  approval_id?: number | null;
  analysis_only?: boolean;
  agent_steps?: AgentStep[];
  agent_reasoning?: AgentReasoning | null;
  export_download?: AdminExportDownloadSpec | null;
  agent_questionnaire?: AgentQuestionnaire | null;
  llm_degraded?: boolean;
  llm_provider?: string | null;
  gpt_slug?: string | null;
  knowledge_hits?: number;
  tools_used?: string[];
  copilot_state?: CopilotState | null;
  answer?: string;
  mode?: 'gemini' | 'gemini_pro' | 'ollama' | 'local_fallback' | string | null;
  confidence?: number | null;
  reasoning_summary?: string | null;
  error?: string | null;
  language?: string | null;
  execution_time_ms?: number | null;
  sources_used?: AiSourceUsed[];
  requires_confirmation?: boolean;
  suggested_action?: Record<string, unknown> | null;
  export_preview?: ExportPreviewPayload | null;
  export_status?: string | null;
  export_result?: ExportExecuteResponse | null;
}

export interface AiSourceUsed {
  chunk_id?: number;
  title?: string;
  score?: number;
  snippet?: string;
}

export interface AiHealthSnapshot {
  active_provider: string;
  status: 'green' | 'orange' | 'red';
  uptime_seconds: number;
  total_requests: number;
  success_requests: number;
  error_requests: number;
  success_rate: number;
  avg_latency_ms: number;
  provider_usage: Record<string, number>;
  tool_usage: Record<string, number>;
  top_tools: { name: string; count: number }[];
  last_error: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminAiService {
  private copilotState: CopilotState | null = null;

  constructor(private readonly http: HttpClient) {}

  getCopilotState(): CopilotState | null {
    return this.copilotState;
  }

  setCopilotState(state: CopilotState | null | undefined): void {
    this.copilotState = state ?? null;
  }

  clearCopilotState(): void {
    this.copilotState = null;
  }

  getOverview(): Observable<AiAssistantOverview> {
    return this.http.get<AiAssistantOverview>(`${API_BASE_URL}/admin/ai-assistant/overview`);
  }

  getHealth(): Observable<AiHealthSnapshot> {
    return this.http.get<AiHealthSnapshot>(`${API_BASE_URL}/admin/ai-assistant/health`);
  }

  executeExport(suggestedAction: Record<string, unknown>): Observable<ExportExecuteResponse> {
    return this.http.post<ExportExecuteResponse>(
      `${API_BASE_URL}/admin/ai-assistant/export/execute`,
      { suggested_action: suggestedAction },
    );
  }

  query(
    message: string,
    quickAction?: string,
    agentMode = false,
    conversationHistory: CopilotHistoryMessage[] = [],
    extras?: {
      imageBase64?: string | null;
      imageMimeType?: string | null;
      attachedDocumentName?: string | null;
    },
  ): Observable<AiAssistantQueryResponse> {
    return this.http
      .post<AiAssistantQueryResponse>(`${API_BASE_URL}/admin/ai-assistant/query`, {
        message,
        quick_action: quickAction ?? null,
        agent_mode: agentMode,
        copilot_state: this.copilotState,
        conversation_history: conversationHistory.map((m) => ({
          role: m.role === 'admin' ? 'user' : m.role === 'agent' ? 'assistant' : m.role,
          content: m.content,
        })),
        image_base64: extras?.imageBase64 ?? null,
        image_mime_type: extras?.imageMimeType ?? null,
        attached_document_name: extras?.attachedDocumentName ?? null,
      })
      .pipe(
        timeout(130000),
        catchError((err) => throwError(() => err)),
      );
  }

  downloadActivityLogsPdf(hours = 2, filename = 'activity-logs.pdf'): Observable<Blob> {
    return this.http
      .get(`${API_BASE_URL}/admin/ai-assistant/export/activity-logs.pdf`, {
        params: { hours },
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          anchor.click();
          URL.revokeObjectURL(url);
        }),
      );
  }

  downloadActivityLogsExcel(hours = 24, filename = 'activity-logs.xlsx'): Observable<Blob> {
    return this.http
      .get(`${API_BASE_URL}/admin/ai-assistant/export/activity-logs.xlsx`, {
        params: { hours },
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          anchor.click();
          URL.revokeObjectURL(url);
        }),
      );
  }

  downloadActivityLogsCsv(hours = 24, filename = 'activity-logs.csv'): Observable<Blob> {
    return this.http
      .get(`${API_BASE_URL}/admin/ai-assistant/export/activity-logs.csv`, {
        params: { hours },
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          anchor.click();
          URL.revokeObjectURL(url);
        }),
      );
  }

  downloadPlatformReportPdf(hours = 24, filename = 'platform-report.pdf'): Observable<Blob> {
    return this.http
      .get(`${API_BASE_URL}/admin/ai-assistant/export/platform-report.pdf`, {
        params: { hours },
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          anchor.click();
          URL.revokeObjectURL(url);
        }),
      );
  }

  downloadContextPdf(
    preset: string,
    limit = 10,
    filename = 'export.pdf',
    module?: string,
    exportToken?: string,
  ): Observable<Blob> {
    const params: Record<string, string | number> = { preset, limit };
    if (module) {
      params['module'] = module;
    }
    if (exportToken) {
      params['export_token'] = exportToken;
    }
    return this.http
      .get(`${API_BASE_URL}/admin/ai-assistant/export/context.pdf`, {
        params,
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          anchor.click();
          URL.revokeObjectURL(url);
        }),
      );
  }

  downloadContextXlsx(
    preset: string,
    exportToken: string,
    filename = 'export.xlsx',
  ): Observable<Blob> {
    return this.http
      .get(`${API_BASE_URL}/admin/ai-assistant/export/context.xlsx`, {
        params: { preset, export_token: exportToken },
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          anchor.click();
          URL.revokeObjectURL(url);
        }),
      );
  }

  downloadTrackingStatusPdf(numbers: string, filename = 'tracking-status.pdf'): Observable<Blob> {
    return this.http
      .get(`${API_BASE_URL}/admin/ai-assistant/export/tracking-status.pdf`, {
        params: { numbers },
        responseType: 'blob',
      })
      .pipe(
        tap((blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          anchor.click();
          URL.revokeObjectURL(url);
        }),
      );
  }
}
