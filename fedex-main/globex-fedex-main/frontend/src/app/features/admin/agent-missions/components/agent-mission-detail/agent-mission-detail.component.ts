import { CommonModule, DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, timer } from 'rxjs';
import { switchMap, takeWhile } from 'rxjs/operators';

import {
  AGENT_OPTIONS,
  AgentMissionDetail,
  AgentMissionMessage,
  AgentMissionsService,
  AgentReasoning,
  AgentStep,
  AgentStepResult,
  MissionStatus,
  parseMissionSchema,
  ScheduleType,
} from '../../../../../core/services/agent-missions.service';
import { AgentMissionSchemaComponent } from '../agent-mission-schema/agent-mission-schema.component';
import { getWorkflowTiming, parseWorkflowBuilder } from '../../workflow-builder.types';

type DetailTab = 'schema' | 'results' | 'logs';
type ExecutionUxPhase = 'intent' | 'tools' | 'thinking';

interface ExecutionUxState {
  phase: ExecutionUxPhase;
  intentText: string;
  toolSteps: string[];
  visibleToolCount: number;
  thinkingLabel: string;
  toolsOpen: boolean;
}

const UX_MIN_DURATION_MS = 58_000;
const UX_PHASE_INTENT_MS = 12_000;
const UX_PHASE_TOOLS_MS = 38_000;
const UX_POLL_MS = 2_500;
const UX_TICK_MS = 400;

const SCHEDULE_LABELS: Record<ScheduleType, string> = {
  now: 'Immédiat',
  datetime: 'Date/heure',
  daily: 'Quotidien',
  weekly: 'Hebdomadaire',
};

const AGENT_TOOL_STEPS: Record<string, string[]> = {
  security: [
    'Connexion au module sécurité',
    'Chargement des incidents récents',
    'Analyse des alertes actives',
  ],
  logs: [
    'Accès au journal d\'activité',
    'Filtrage des événements récents',
    'Préparation de la synthèse',
  ],
  support: [
    'Connexion au module support',
    'Chargement des tickets ouverts',
    'Tri par priorité',
  ],
  users: [
    'Accès à l\'annuaire utilisateurs',
    'Chargement des comptes actifs',
    'Vérification des statuts',
  ],
  tracking: [
    'Connexion au suivi expéditions',
    'Chargement des colis en transit',
    'Détection des retards',
  ],
  reports: [
    'Accès aux rapports disponibles',
    'Chargement des métriques',
    'Préparation de la synthèse',
  ],
};

@Component({
  selector: 'app-agent-mission-detail',
  standalone: true,
  imports: [CommonModule, DatePipe, RouterLink, AgentMissionSchemaComponent],
  templateUrl: './agent-mission-detail.component.html',
  styleUrl: './agent-mission-detail.component.scss',
})
export class AgentMissionDetailComponent implements OnInit, OnDestroy {
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly mission = signal<AgentMissionDetail | null>(null);
  readonly activeTab = signal<DetailTab>('schema');
  readonly agentOptions = AGENT_OPTIONS;
  readonly executionUx = signal<ExecutionUxState | null>(null);
  readonly blockingMissionId = signal<number | null>(null);

  private missionId = 0;
  private uxStartedAt = 0;
  private backendFinished = false;
  private uxTickTimer: ReturnType<typeof setInterval> | null = null;
  private pollSub: Subscription | null = null;
  private runSub: Subscription | null = null;

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

  ngOnDestroy(): void {
    this.teardownExecutionUx();
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

  private refreshMissionSilent(): void {
    this.api.get(this.missionId).subscribe({
      next: (m) => {
        this.mission.set(m);
        if (this.executionUx() && (m.status === 'running' || m.status === 'waiting_permission')) {
          this.tryFinishExecutionUx();
        }
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

  scheduleDisplayLabel(m: AgentMissionDetail): string {
    const timing = getWorkflowTiming(m.plan_json);
    const base = SCHEDULE_LABELS[timing.scheduleType] || timing.scheduleType;
    if (timing.scheduleType === 'datetime' && (timing.scheduledAt || m.scheduled_at)) {
      const raw = timing.scheduledAt || m.scheduled_at;
      if (raw) {
        try {
          return new Date(raw).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
        } catch {
          return base;
        }
      }
    }
    if ((timing.scheduleType === 'daily' || timing.scheduleType === 'weekly') && timing.scheduleTime) {
      return `${base} à ${timing.scheduleTime}`;
    }
    return base;
  }

  statusLabel(status: MissionStatus): string {
    const map: Record<MissionStatus, string> = {
      draft: 'Prête à lancer',
      waiting_plan_approval: 'Prête à lancer',
      scheduled: 'Planifiée',
      running: 'En cours',
      paused: 'En pause',
      waiting_permission: 'Permission requise',
      completed: 'Terminée',
      failed: 'Échouée',
      cancelled: 'Annulée',
    };
    return map[status] || status;
  }

  run(): void {
    const m = this.mission();
    if (!m) return;
    this.startExecutionFlow(() => this.api.run(this.missionId));
  }

  pause(): void {
    this.busy.set(true);
    this.api.pause(this.missionId).subscribe({
      next: () => {
        this.busy.set(false);
        this.teardownExecutionUx();
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Pause impossible.');
        this.busy.set(false);
      },
    });
  }

  resume(): void {
    const m = this.mission();
    if (!m) return;
    this.startExecutionFlow(() => this.api.resume(this.missionId));
  }

  private startExecutionFlow(runCall: () => ReturnType<AgentMissionsService['run']>): void {
    const m = this.mission();
    if (!m) return;

    this.busy.set(true);
    this.error.set(null);
    this.blockingMissionId.set(null);
    this.backendFinished = false;
    this.activeTab.set('results');
    this.beginExecutionUx(m);
    this.startMissionPolling();

    this.runSub?.unsubscribe();
    this.runSub = runCall().subscribe({
      next: () => {
        this.backendFinished = true;
        this.refreshMissionSilent();
        this.tryFinishExecutionUx();
      },
      error: (err: HttpErrorResponse) => {
        this.backendFinished = true;
        const detail = err.error?.detail || 'Exécution impossible.';
        this.error.set(detail);
        this.parseBlockingMissionId(detail);
        this.teardownExecutionUx();
        this.busy.set(false);
        this.load();
      },
    });
  }

  private beginExecutionUx(m: AgentMissionDetail): void {
    this.teardownExecutionUx(false);
    this.uxStartedAt = Date.now();
    this.executionUx.set({
      phase: 'intent',
      intentText: this.buildIntentNarrative(m),
      toolSteps: this.buildToolSteps(m),
      visibleToolCount: 0,
      thinkingLabel: 'Analyse des données collectées…',
      toolsOpen: true,
    });

    this.uxTickTimer = setInterval(() => this.advanceUxPhase(), UX_TICK_MS);
  }

  private advanceUxPhase(): void {
    const ux = this.executionUx();
    if (!ux) return;

    const elapsed = Date.now() - this.uxStartedAt;
    let phase: ExecutionUxPhase = 'intent';
    if (elapsed >= UX_PHASE_TOOLS_MS) {
      phase = 'thinking';
    } else if (elapsed >= UX_PHASE_INTENT_MS) {
      phase = 'tools';
    }

    const toolProgress = Math.min(
      ux.toolSteps.length,
      Math.floor((elapsed - UX_PHASE_INTENT_MS) / 2_800) + 1,
    );
    const thinkingLabels = [
      'Analyse des données collectées…',
      'Croisement des informations…',
      'Formulation de la réponse…',
    ];
    const thinkingIdx = Math.min(
      thinkingLabels.length - 1,
      Math.floor((elapsed - UX_PHASE_TOOLS_MS) / 4_500),
    );

    this.executionUx.set({
      ...ux,
      phase,
      visibleToolCount: phase === 'intent' ? 0 : Math.max(0, toolProgress),
      thinkingLabel: thinkingLabels[Math.max(0, thinkingIdx)],
    });

    this.tryFinishExecutionUx();
  }

  private tryFinishExecutionUx(): void {
    if (!this.backendFinished || !this.executionUx()) return;
    const elapsed = Date.now() - this.uxStartedAt;
    if (elapsed < UX_MIN_DURATION_MS) return;

    this.teardownExecutionUx();
    this.busy.set(false);
    this.load();
  }

  private teardownExecutionUx(clearUx = true): void {
    if (this.uxTickTimer) {
      clearInterval(this.uxTickTimer);
      this.uxTickTimer = null;
    }
    this.pollSub?.unsubscribe();
    this.pollSub = null;
    this.runSub?.unsubscribe();
    this.runSub = null;
    if (clearUx) {
      this.executionUx.set(null);
    }
  }

  private startMissionPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = timer(UX_POLL_MS, UX_POLL_MS)
      .pipe(
        takeWhile(() => !this.backendFinished),
        switchMap(() => this.api.get(this.missionId)),
      )
      .subscribe({
        next: (m) => this.mission.set(m),
      });
  }

  private buildIntentNarrative(m: AgentMissionDetail): string {
    const desc = (m.task_description || '').trim();
    if (!desc) {
      return `Je vais exécuter cette mission avec l'agent ${this.agentLabel(m.agent_type)}.`;
    }
    const lower = desc.charAt(0).toLowerCase() + desc.slice(1);
    if (/^(je |j'|lister|analyser|afficher|produire|détecter|exporter|vérifier|suspendre|marquer|partager|préparer)/i.test(desc)) {
      return `Je vais ${lower.replace(/\.$/, '')} et vous présenter une synthèse claire.`;
    }
    return `Je vais traiter votre demande : ${desc.replace(/\.$/, '')}.`;
  }

  private buildToolSteps(m: AgentMissionDetail): string[] {
    const agentKey = m.agent_type === 'notifications' ? 'security' : m.agent_type === 'summary' ? 'reports' : m.agent_type;
    return AGENT_TOOL_STEPS[agentKey] || [
      'Initialisation de l\'agent',
      'Chargement du contexte mission',
      'Préparation des outils métier',
    ];
  }

  private parseBlockingMissionId(detail: string): void {
    const match = detail.match(/#(\d+)/);
    this.blockingMissionId.set(match ? Number(match[1]) : null);
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
    return m.status === 'running' || !!this.executionUx();
  }

  showFinalResults(m: AgentMissionDetail): boolean {
    return !this.executionUx() && (m.results.has_results || !!m.messages.length || m.status === 'running');
  }

  chatMessages(m: AgentMissionDetail): AgentMissionMessage[] {
    if (this.executionUx()) {
      const adminOnly: AgentMissionMessage[] = [];
      if (m.task_description) {
        adminOnly.push({
          id: 0,
          mission_id: m.id,
          sender: 'admin',
          content: m.task_description,
          metadata_json: '{}',
          created_at: m.created_at,
        });
      }
      return adminOnly;
    }
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
    if (this.executionUx()) return [];
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
    if (this.executionUx()) return null;
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
    if (this.executionUx()) return 'EN COURS';
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

  uxPhaseAtLeast(phase: ExecutionUxPhase, target: ExecutionUxPhase): boolean {
    const order: ExecutionUxPhase[] = ['intent', 'tools', 'thinking'];
    return order.indexOf(phase) >= order.indexOf(target);
  }
}
