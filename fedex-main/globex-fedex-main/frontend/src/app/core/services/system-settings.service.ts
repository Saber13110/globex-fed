import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';
import { AdminDashboardStats } from './admin.service';

export interface NotificationSettings {
  email: boolean;
  sms: boolean;
  in_app: boolean;
  critical_alerts: boolean;
}

export interface SecuritySettings {
  mfa_enabled: boolean;
}

export interface SmtpIntegrationSettings {
  host: string;
  port: number;
  user: string;
  use_tls: boolean;
  password_set: boolean;
}

export interface IntegrationSettings {
  smtp: SmtpIntegrationSettings;
}

export interface AiSettings {
  provider: 'gemini' | 'openai' | 'claude' | 'ollama';
  temperature: number;
  max_tokens: number;
  system_prompt: string;
}

export interface SystemSettingsPayload {
  notifications: NotificationSettings;
  security: SecuritySettings;
  integrations: IntegrationSettings;
  ai: AiSettings;
  updated_at?: string | null;
}

export interface SystemSettingsPatch {
  notifications?: NotificationSettings;
  security?: SecuritySettings;
  integrations?: IntegrationSettings;
  ai?: AiSettings;
}

export interface ServiceHealthItem {
  key: string;
  label: string;
  status: 'online' | 'offline' | 'degraded' | 'disabled' | 'not_configured';
  availability_percent: number;
  latency_ms: number | null;
  last_check: string;
  detail: string;
}

export interface SystemHealthResponse {
  services: ServiceHealthItem[];
}

export interface SystemInfoResponse {
  version: string;
  environment: string;
  database_status: string;
  server: string;
  last_updated: string;
}

export interface SystemOperationResponse {
  ok: boolean;
  message: string;
  detail?: Record<string, unknown> | null;
}

export interface IntegrationTestResponse {
  ok: boolean;
  provider: string;
  message: string;
  latency_ms: number | null;
}

@Injectable({ providedIn: 'root' })
export class SystemSettingsService {
  constructor(private readonly http: HttpClient) {}

  getDashboardStats(): Observable<AdminDashboardStats> {
    return this.http.get<AdminDashboardStats>(`${API_BASE_URL}/api/dashboard/stats`);
  }

  getSettings(): Observable<SystemSettingsPayload> {
    return this.http.get<SystemSettingsPayload>(`${API_BASE_URL}/api/settings`);
  }

  patchSettings(payload: SystemSettingsPatch): Observable<SystemSettingsPayload> {
    return this.http.patch<SystemSettingsPayload>(`${API_BASE_URL}/api/settings`, payload);
  }

  getHealth(): Observable<SystemHealthResponse> {
    return this.http.get<SystemHealthResponse>(`${API_BASE_URL}/api/system/health`);
  }

  getSystemInfo(): Observable<SystemInfoResponse> {
    return this.http.get<SystemInfoResponse>(`${API_BASE_URL}/api/settings/info`);
  }

  clearCache(): Observable<SystemOperationResponse> {
    return this.http.post<SystemOperationResponse>(`${API_BASE_URL}/api/system/cache/clear`, {});
  }

  reindex(): Observable<SystemOperationResponse> {
    return this.http.post<SystemOperationResponse>(`${API_BASE_URL}/api/system/reindex`, {});
  }

  backup(): Observable<SystemOperationResponse> {
    return this.http.post<SystemOperationResponse>(`${API_BASE_URL}/api/system/backup`, {});
  }

  testEmail(to: string): Observable<{ sent: boolean }> {
    return this.http.post<{ sent: boolean }>(`${API_BASE_URL}/api/settings/test-email`, { to });
  }

  changePassword(current: string, newPassword: string, confirm: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${API_BASE_URL}/api/settings/change-password`, {
      current_password: current,
      new_password: newPassword,
      confirm_password: confirm,
    });
  }

  testFedex(): Observable<IntegrationTestResponse> {
    return this.http.post<IntegrationTestResponse>(`${API_BASE_URL}/api/settings/integrations/fedex/test`, {});
  }

  testGemini(): Observable<IntegrationTestResponse> {
    return this.http.post<IntegrationTestResponse>(`${API_BASE_URL}/api/settings/integrations/gemini/test`, {});
  }

  testOpenai(): Observable<IntegrationTestResponse> {
    return this.http.post<IntegrationTestResponse>(`${API_BASE_URL}/api/settings/integrations/openai/test`, {});
  }
}
