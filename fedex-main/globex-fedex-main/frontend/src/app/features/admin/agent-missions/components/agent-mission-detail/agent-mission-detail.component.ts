import { CommonModule, DatePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, RouterLink } from '@angular/router';

import {
  AGENT_OPTIONS,
  AgentMissionDetail,
  AgentMissionMessage,
  AgentMissionsService,
  AgentReasoning,
  AgentStep,
  AgentStepResult,
  MissionStatus,
  MissionWorkflowSchema,
  parseMissionSchema,
} from '../../../../../core/services/agent-missions.service';
import { AgentMissionSchemaComponent } from '../agent-mission-schema/agent-mission-schema.component';
import { parseWorkflowBuilder } from '../../workflow-builder.types';

type DetailTab = 'schema' | 'results' | 'logs';

@Component({
  selector: 'app-agent-mission-detail',
  standalone: true,
  imports: [CommonModule, DatePipe, RouterLink, AgentMissionSchemaComponent],
  templateUrl: './agent-mission-detail.component.html',
  styleUrl: './agent-mission-detail.component.scss',
})
export class AgentMissionDetailComponent implements OnInit {
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly mission = signal<AgentMissionDetail | null>(null);
  readonly activeTab = signal<DetailTab>('schema');
  readonly agentOptions = AGENT_OPTIONS;

  private missionId = 0;

  constructor(
    private readonly api: AgentMissionsService,
    private readonly route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.route.paramMap.subscribe((params) => {
      const id = Number(params.get('id'));
      if (!Number.isFinite(id) || id <= 0) {
        this.error.set('Mission invalide.');
        this.loading.set(false);
        return;
      }
      this.missionId = id;
      this.load();
    });
    this.route.queryParamMap.subscribe((params) => {
      const tab = params.get('tab');
      if (tab === 'results' || tab === 'schema' || tab === 'logs') {
        this.activeTab.set(tab);
      }
    });
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.get(this.missionId).subscribe({
      next: (m) => {
        this.mission.set(m);
        const forcedTab = this.route.snapshot.queryParamMap.get('tab');
        if (forcedTab === 'results' || forcedTab === 'schema' || forcedTab === 'logs') {
          this.activeTab.set(forcedTab);
        } else {
          this.activeTab.set(m.results?.has_results ? 'results' : 'schema');
        }
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Mission introuvable.');
        this.loading.set(false);
      },
    });
  }

  workflowSchema(m: AgentMissionDetail): ReturnType<typeof parseMissionSchema> {
    const builder = parseWorkflowBuilder(m.plan_json);
    if (builder) return null;
    return parseMissionSchema(m.plan_json);
  }

  hasBuilderWorkflow(m: AgentMissionDetail): boolean {
    return !!parseWorkflowBuilder(m.plan_json);
  }

  hasRoleMismatch(m: AgentMissionDetail): boolean {
    return m.results.step_results.some((s) => s.output['role_mismatch'] === true);
  }

  agentLabel(type: string): string {
    return this.agentOptions.find((a) => a.value === type)?.label || type;
  }

  statusLabel(status: MissionStatus): string {
    const map: Record<MissionStatus, string> = {
      draft: 'Prête à lancer',
      waiting_plan_approval: 'Prête à lancer',
      scheduled: 'Planifiée',
      running: 'En cours',
      waiting_permission: 'Permission requise',
      completed: 'Terminée',
      failed: 'Échouée',
      cancelled: 'Annulée',
    };
    return map[status] || status;
  }

  run(): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.run(this.missionId).subscribe({
      next: () => {
        this.busy.set(false);
        this.activeTab.set('results');
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Exécution impossible.');
        this.busy.set(false);
        this.load();
      },
    });
  }

  approveAction(approvalId: number): void {
    this.busy.set(true);
    this.api.approveAction(approvalId).subscribe({
      next: () => {
        this.busy.set(false);
        this.activeTab.set('results');
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Approbation impossible.');
        this.busy.set(false);
      },
    });
  }

  rejectAction(approvalId: number): void {
    this.busy.set(true);
    this.api.rejectAction(approvalId).subscribe({
      next: () => {
        this.busy.set(false);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Refus impossible.');
        this.busy.set(false);
      },
    });
  }

  actionExecuted(m: AgentMissionDetail): boolean {
    return m.results.step_results.some((s) => s.output['action_executed'] === true);
  }

  needsApproval(m: AgentMissionDetail): boolean {
    return m.status === 'waiting_permission' || m.results.step_results.some((s) => s.output['needs_approval'] === true);
  }

  stepStatusLabel(status: string): string {
    const map: Record<string, string> = {
      pending: 'En attente',
      running: 'En cours',
      completed: 'Terminée',
      failed: 'Échouée',
      skipped: 'Ignorée',
      waiting_approval: 'Approbation requise',
    };
    return map[status] || status;
  }

  setTab(tab: DetailTab): void {
    this.activeTab.set(tab);
  }

  metricLabel(key: string): string {
    const map: Record<string, string> = {
      task_answer: 'Réponse à votre tâche',
      total_logs: 'Logs totaux',
      sample_count: 'Échantillon analysé',
      warning_critical_count: 'Alertes WARNING/CRITICAL',
      open_tickets: 'Tickets ouverts',
      urgent_candidates: 'Tickets urgents',
      total_users: 'Utilisateurs',
      reviewed: 'Comptes analysés',
      shipments_reviewed: 'Expéditions analysées',
      delays_found: 'Retards détectés',
      notifications_reviewed: 'Notifications analysées',
      notifications_unread: 'Notifications non lues',
      attack_related_notifications: 'Alertes sécurité (notifications)',
      security_incidents_open: 'Incidents sécurité ouverts',
      action_executed: 'Action exécutée',
      needs_approval: 'Approbation requise',
      analysis_only: 'Analyse seulement',
      intent: 'Intention détectée',
      verification: 'Vérification',
      target_user: 'Utilisateur cible',
    };
    return map[key] || key.replace(/_/g, ' ');
  }

  formatOutputValue(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  }

  outputEntries(step: AgentStepResult): { key: string; value: string }[] {
    return Object.entries(step.output)
      .filter(
        ([key]) =>
          ![
            'action',
            'simulated',
            'task_answer',
            'summary',
            'analysis',
            'task',
            'role_mismatch',
            'suggested_agent',
            'suggested_agent_label',
            'context_snapshot',
            'approval_payload',
          ].includes(key),
      )
      .map(([key, value]) => ({ key, value: this.formatOutputValue(value) }));
  }

  taskAnswer(step: AgentStepResult): string {
    const answer = step.output['task_answer'] || step.output['summary'] || step.output['analysis'];
    return typeof answer === 'string' ? answer : '';
  }

  isRunning(m: AgentMissionDetail): boolean {
    return m.status === 'running';
  }

  chatMessages(m: AgentMissionDetail): AgentMissionMessage[] {
    if (m.messages?.length) return m.messages;
    const fallback: AgentMissionMessage[] = [];
    if (m.task_description) {
      fallback.push({
        id: 0,
        mission_id: m.id,
        sender: 'admin',
        content: m.task_description,
        metadata_json: '{}',
        created_at: m.created_at,
      });
    }
    for (const step of m.results.step_results) {
      const answer = this.taskAnswer(step);
      if (answer) {
        fallback.push({
          id: step.step_id,
          mission_id: m.id,
          sender: 'agent',
          content: answer,
          metadata_json: JSON.stringify({
            agent_steps: step.output['agent_steps'],
            agent_reasoning: step.output['agent_reasoning'],
          }),
          created_at: m.finished_at || m.updated_at,
        });
      }
    }
    return fallback;
  }

  messageMeta(msg: AgentMissionMessage): {
    agent_steps?: AgentStep[];
    agent_reasoning?: AgentReasoning;
    action_executed?: boolean;
    needs_approval?: boolean;
  } {
    try {
      return JSON.parse(msg.metadata_json || '{}') as {
        agent_steps?: AgentStep[];
        agent_reasoning?: AgentReasoning;
        action_executed?: boolean;
        needs_approval?: boolean;
      };
    } catch {
      return {};
    }
  }

  displaySteps(m: AgentMissionDetail): AgentStep[] {
    if (m.agent_steps?.length) return m.agent_steps;
    const msgs = [...(m.messages || [])].reverse();
    for (const msg of msgs) {
      const steps = this.messageMeta(msg).agent_steps;
      if (steps?.length) return steps;
    }
    for (const step of [...m.results.step_results].reverse()) {
      const steps = step.output['agent_steps'];
      if (Array.isArray(steps) && steps.length) return steps as AgentStep[];
    }
    return [];
  }

  displayReasoning(m: AgentMissionDetail): AgentReasoning | null {
    if (m.agent_reasoning) return m.agent_reasoning;
    const msgs = [...(m.messages || [])].reverse();
    for (const msg of msgs) {
      const reasoning = this.messageMeta(msg).agent_reasoning;
      if (reasoning) return reasoning;
    }
    for (const step of [...m.results.step_results].reverse()) {
      const reasoning = step.output['agent_reasoning'];
      if (reasoning && typeof reasoning === 'object') return reasoning as AgentReasoning;
    }
    return null;
  }

  actionStatusLabel(m: AgentMissionDetail): string {
    if (this.actionExecuted(m)) return 'FAIT';
    if (this.needsApproval(m)) return 'EN ATTENTE';
    if (m.status === 'running') return 'EN COURS';
    const summary = m.results.executive_summary || '';
    if (summary.startsWith('NON FAIT') || summary.startsWith('PARTIEL')) return 'NON FAIT';
    if (m.results.has_results) return 'ANALYSE';
    return '—';
  }

  stepDotClass(status: string): string {
    if (status === 'done' || status === 'completed') return 'is-done';
    if (status === 'running') return 'is-running';
    if (status === 'error' || status === 'failed') return 'is-error';
    if (status === 'warning') return 'is-warning';
    return 'is-pending';
  }
}
