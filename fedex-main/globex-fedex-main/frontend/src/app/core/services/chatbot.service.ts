import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';
import { ChatImageAttachment, AgentQuestionnaire, AgentReasoning, AgentStep, AgentSuggestion } from '../models/chat-send.model';

export interface TrackingEvent {
  at: string;
  description: string;
  location: string;
}

export interface VisibilityEvent {
  id?: number;
  tracking_number: string;
  event_type: string;
  event_type_label?: string;
  event_code?: string | null;
  description: string;
  location?: string | null;
  occurred_at?: string | null;
  source?: string | null;
}

export interface PodInfo {
  tracking_number: string;
  status?: string | null;
  delivered_at?: string | null;
  delivered_time?: string | null;
  delivery_address?: string | null;
  received_by_name?: string | null;
  signature_available?: boolean;
  carrier_service?: string | null;
  current_location?: string | null;
  source?: string | null;
}

export interface TrackingMapPoint {
  step: number;
  date: string;
  eventDescription: string;
  city: string;
  stateOrProvinceCode: string;
  countryCode: string;
  countryName: string;
  latitude?: number | null;
  longitude?: number | null;
  kind?: string;
  label?: string;
}

export interface ShipmentMapPoint {
  label: string;
  lat: number;
  lng: number;
  kind?: string;
  description?: string;
}

export interface ShipmentSummary {
  tracking_number: string;
  status: string | null;
  status_code?: string | null;
  status_description?: string | null;
  current_location: string | null;
  city?: string | null;
  state_or_province?: string | null;
  country?: string | null;
  estimated_delivery: string | null;
  actual_delivery?: string | null;
  events?: TrackingEvent[];
  visibility_events?: VisibilityEvent[];
  service_type?: string | null;
  service_description?: string | null;
  shipper?: string | null;
  recipient?: string | null;
  origin_location?: string | null;
  destination_location?: string | null;
  weight?: string | null;
  dimensions?: string | null;
  package_type?: string | null;
  package_count?: string | null;
  special_handlings?: { type: string; description: string; payment_type?: string }[];
  delivery_details?: Record<string, unknown> | null;
  received_by_name?: string | null;
  available_images?: { type: string; size?: string }[];
  available_notifications?: string[];
  hold_at_location?: Record<string, unknown> | null;
  service_commit_message?: string | null;
  pod_available?: boolean;
  pod_info?: PodInfo | null;
  source?: string | null;
  sandbox_whitelist_denied?: boolean;
  map_points?: TrackingMapPoint[];
  map_available?: boolean;
  show_tracking_map?: boolean;
  show_timeline?: boolean;
  timeline_total?: number;
  delivered?: boolean;
  raw?: Record<string, unknown> | null;
}

export interface ExportDownloadSpec {
  session_id: number;
  tracking_numbers: string[];
  preset?: string;
  include_events?: boolean;
  export_token?: string | null;
  filename?: string | null;
  format?: string | null;
}

export interface ChatMessageResponse {
  reply: string;
  session_id: number;
  session_title?: string | null;
  source: 'fedex_api' | 'fedex_api+ollama' | 'gemini' | 'ollama' | 'llm' | 'export' | 'export_prompt' | 'fallback' | 'unknown' | 'agent';
  shipment: ShipmentSummary | null;
  export_download?: ExportDownloadSpec | null;
  intent?: string | null;
  tracking_number?: string | null;
  llm_provider?: string | null;
  agent_mode?: boolean;
  agent_phase?: string | null;
  agent_questionnaire?: AgentQuestionnaire | null;
  agent_steps?: AgentStep[];
  agent_reasoning?: AgentReasoning | null;
  agent_suggestion?: AgentSuggestion | null;
}

export interface ChatPromptContext {
  response_preferences?: string;
  preferred_name?: string;
  ui_language?: string;
  image?: ChatImageAttachment;
  agent_mode?: boolean;
  agent_flow_id?: string;
  agent_answers?: Record<string, string>;
}

@Injectable({ providedIn: 'root' })
export class ChatbotService {
  constructor(private readonly http: HttpClient) {}

  sendMessage(message: string, sessionId?: number | null, context?: ChatPromptContext): Observable<ChatMessageResponse> {
    return this.http.post<ChatMessageResponse>(`${API_BASE_URL}/chat/message`, {
      message: message ?? '',
      session_id: sessionId ?? null,
      response_preferences: context?.response_preferences ?? null,
      preferred_name: context?.preferred_name ?? null,
      ui_language: context?.ui_language ?? null,
      image_base64: context?.image?.base64 ?? null,
      image_mime_type: context?.image?.mimeType ?? null,
      file_name: context?.image?.name ?? null,
      agent_mode: context?.agent_mode ?? false,
      agent_flow_id: context?.agent_flow_id ?? null,
      agent_answers: context?.agent_answers ?? null,
    });
  }
}
