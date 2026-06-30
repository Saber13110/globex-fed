import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export type AgentType =
  | 'logs'
  | 'support'
  | 'users'
  | 'tracking'
  | 'security'
  | 'reports'
  | 'notifications'
  | 'summary';
export type ScheduleType = 'now' | 'datetime' | 'daily' | 'weekly';
export type MissionStatus =
  | 'draft'
  | 'waiting_plan_approval'
  | 'scheduled'
  | 'running'
  | 'paused'
  | 'waiting_permission'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface AgentMissionStep {
  id: number;
  step_order: number;
  title: string;
  description: string;
  action_type: string;
  is_sensitive: boolean;
  status: string;
  output_json: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AgentApproval {
  id: number;
  mission_id: number;
  step_id: number;
  action_type: string;
  description: string;
  payload_json: string;
  status: string;
  resolved_by_admin_id: number | null;
  resolved_at: string | null;
  created_at: string;
}

export interface AgentExecutionLog {
  id: number;
  mission_id: number;
  step_id: number | null;
  level: string;
  message: string;
  details_json: string;
  created_at: string;
}

export interface AgentMission {
  id: number;
  admin_id: number;
  agent_type: AgentType;
  task_description: string;
  status: MissionStatus;
  schedule_type: ScheduleType;
  scheduled_at: string | null;
  schedule_time: string;
  max_items: number;
  max_duration_minutes: number;
  require_approval_sensitive: boolean;
  notify_on_start: boolean;
  notify_on_complete: boolean;
  plan_json: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancelled_at: string | null;
  steps: AgentMissionStep[];
  pending_approvals: AgentApproval[];
}

export interface AgentMissionMessage {
  id: number;
  mission_id: number;
  sender: 'admin' | 'agent' | 'system' | string;
  content: string;
  metadata_json: string;
  created_at: string;
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

export interface AgentMissionDetail extends AgentMission {
  logs: AgentExecutionLog[];
  messages: AgentMissionMessage[];
  agent_steps: AgentStep[];
  agent_reasoning: AgentReasoning | null;
  results: AgentMissionResults;
}

export interface AgentStepResult {
  step_id: number;
  step_order: number;
  title: string;
  action_type: string;
  status: string;
  output: Record<string, unknown>;
}

export interface AgentMissionResults {
  has_results: boolean;
  executive_summary: string;
  metrics: Record<string, unknown>;
  step_results: AgentStepResult[];
}

export interface MissionWorkflowSchema {
  version: number;
  type: string;
  trigger: { id: string; label: string; description: string };
  agent: { id: string; label: string; description: string };
  tools: { id: string; label: string }[];
  decision: {
    id: string;
    label: string;
    yes_label: string;
    no_label: string;
    matches?: boolean | null;
    reason?: string;
    suggested_agent?: string | null;
  };
  outcomes: {
    success: { label: string; description: string };
    rejected: { label: string; description: string };
  };
  task?: string;
}

export function parseMissionSchema(planJson: string): MissionWorkflowSchema | null {
  if (!planJson?.trim()) return null;
  try {
    const data = JSON.parse(planJson) as MissionWorkflowSchema;
    if (data?.version === 2 && data.type === 'workflow') return data;
    return null;
  } catch {
    return null;
  }
}

export interface AgentMissionListItem {
  id: number;
  agent_type: AgentType;
  task_description: string;
  status: MissionStatus;
  schedule_type: ScheduleType;
  scheduled_at: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  has_results: boolean;
  result_preview: string;
}

export interface AgentMissionListResponse {
  items: AgentMissionListItem[];
  total: number;
  stats: {
    total: number;
    waiting_plan_approval: number;
    running: number;
    completed: number;
  };
}

export interface AgentMissionCreate {
  agent_type: AgentType;
  task_description: string;
  schedule_type: ScheduleType;
  scheduled_at?: string | null;
  schedule_time?: string;
  max_items?: number;
  max_duration_minutes?: number;
  require_approval_sensitive?: boolean;
  notify_on_start?: boolean;
  notify_on_complete?: boolean;
  plan_json?: string;
}

export const AGENT_OPTIONS: { value: AgentType; label: string }[] = [
  { value: 'logs', label: 'Logs Agent' },
  { value: 'support', label: 'Support Agent' },
  { value: 'users', label: 'Users Agent' },
  { value: 'security', label: 'Security Agent' },
  { value: 'tracking', label: 'Tracking Agent' },
  { value: 'reports', label: 'Reports Agent' },
];

export const SCHEDULE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: 'now', label: 'Maintenant' },
  { value: 'datetime', label: 'Date/heure précise' },
  { value: 'daily', label: 'Tous les jours' },
  { value: 'weekly', label: 'Chaque semaine' },
];

@Injectable({ providedIn: 'root' })
export class AgentMissionsService {
  private readonly base = `${API_BASE_URL}/admin/agent-missions`;

  constructor(private readonly http: HttpClient) {}

  list(): Observable<AgentMissionListResponse> {
    return this.http.get<AgentMissionListResponse>(this.base);
  }

  get(id: number): Observable<AgentMissionDetail> {
    return this.http.get<AgentMissionDetail>(`${this.base}/${id}`);
  }

  create(payload: AgentMissionCreate): Observable<AgentMission> {
    return this.http.post<AgentMission>(this.base, payload);
  }

  createWithWorkflow(payload: AgentMissionCreate): Observable<AgentMission> {
    return this.http.post<AgentMission>(this.base, payload);
  }

  updateWorkflow(id: number, payload: AgentMissionCreate): Observable<AgentMission> {
    return this.http.patch<AgentMission>(`${this.base}/${id}/workflow`, payload);
  }

  generatePlan(id: number): Observable<AgentMission> {
    return this.http.post<AgentMission>(`${this.base}/${id}/generate-plan`, {});
  }

  approvePlan(id: number): Observable<AgentMission> {
    return this.http.post<AgentMission>(`${this.base}/${id}/approve-plan`, {});
  }

  run(id: number): Observable<AgentMission> {
    return this.http.post<AgentMission>(`${this.base}/${id}/run`, {});
  }

  cancel(id: number): Observable<AgentMission> {
    return this.http.post<AgentMission>(`${this.base}/${id}/cancel`, {});
  }

  pause(id: number): Observable<AgentMission> {
    return this.http.post<AgentMission>(`${this.base}/${id}/pause`, {});
  }

  resume(id: number): Observable<AgentMission> {
    return this.http.post<AgentMission>(`${this.base}/${id}/resume`, {});
  }

  logs(id: number): Observable<AgentExecutionLog[]> {
    return this.http.get<AgentExecutionLog[]>(`${this.base}/${id}/logs`);
  }

  results(id: number): Observable<AgentMissionResults> {
    return this.http.get<AgentMissionResults>(`${this.base}/${id}/results`);
  }

  approveAction(approvalId: number): Observable<{ approval: AgentApproval; mission: AgentMission }> {
    return this.http.post<{ approval: AgentApproval; mission: AgentMission }>(
      `${API_BASE_URL}/admin/agent-approvals/${approvalId}/approve`,
      {},
    );
  }

  rejectAction(approvalId: number): Observable<{ approval: AgentApproval; mission: AgentMission }> {
    return this.http.post<{ approval: AgentApproval; mission: AgentMission }>(
      `${API_BASE_URL}/admin/agent-approvals/${approvalId}/reject`,
      {},
    );
  }
}
