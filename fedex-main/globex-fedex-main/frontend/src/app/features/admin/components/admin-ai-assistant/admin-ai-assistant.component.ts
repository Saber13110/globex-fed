import { animate, style, transition, trigger } from '@angular/animations';
import { CommonModule } from '@angular/common';
import {
  Component,
  ElementRef,
  OnInit,
  ViewChild,
  computed,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  AdminAiService,
  AdminExportDownloadSpec,
  AiAssistantOverview,
  CopilotAttachmentDisplay,
  CopilotChatMessage,
} from '../../../../core/services/admin-ai.service';
import { GptKnowledgeService } from '../../../../core/services/gpt-knowledge.service';
import {
  COPILOT_ALLOWED_EXTENSIONS,
  MAX_COPILOT_FILE_BYTES,
  PendingCopilotFile,
  copilotFileIcon,
  copilotFileKind,
} from './admin-ai-assistant.attachments';
import { AgentMissionsService } from '../../../../core/services/agent-missions.service';
import { AgentQuestionnaire } from '../../../../core/models/chat-send.model';
import { AgentQuestionnaireComponent } from '../../../chat/components/agent-questionnaire/agent-questionnaire.component';
import { ChatFormattedTextPipe } from '../../../../shared/pipes/chat-formatted-text.pipe';

const QUICK_ACTION_MAP: Record<string, string> = {
  'analyze shipment delays': 'delays',
  'top exceptions today': 'exceptions',
  'generate performance report': 'report',
  'view user activity': 'activity',
  'compare countries': 'countries',
  'predict delivery issues': 'predict',
};

interface QuickActionCard {
  title: string;
  description: string;
  icon: 'truck' | 'report' | 'globe' | 'spark' | 'users' | 'alert';
}

interface ConversationRow {
  id: number | string;
  question: string;
  status: string;
  created_at: string;
  relative: string;
}

const QUICK_ACTION_CARDS: QuickActionCard[] = [
  { title: 'Analyze shipment delays', description: 'Identify delayed shipments and root causes.', icon: 'truck' },
  { title: 'Generate performance report', description: 'Create detailed performance reports.', icon: 'report' },
  { title: 'Compare countries', description: 'Compare delivery performance by country.', icon: 'globe' },
  { title: 'Predict delivery issues', description: 'AI predictions for potential delivery issues.', icon: 'spark' },
  { title: 'View user activity', description: 'Analyze user operations and activities.', icon: 'users' },
  { title: 'Top exceptions today', description: 'View top exceptions that need attention.', icon: 'alert' },
];

const DEMO_CONVERSATIONS: ConversationRow[] = [
  { id: 'd1', question: 'Show me delayed shipments from New York', status: 'completed', created_at: '', relative: '5 min ago' },
  { id: 'd2', question: 'Generate weekly performance report', status: 'completed', created_at: '', relative: '15 min ago' },
  { id: 'd3', question: 'Why are there so many exceptions this week?', status: 'completed', created_at: '', relative: '30 min ago' },
  { id: 'd4', question: 'Compare delivery performance: USA vs Canada', status: 'completed', created_at: '', relative: '1 hour ago' },
  { id: 'd5', question: 'Predict delays for tomorrow', status: 'processing', created_at: '', relative: '2 hours ago' },
  { id: 'd6', question: 'Show top 5 exceptions requiring attention', status: 'completed', created_at: '', relative: '3 hours ago' },
];

const KB_FILE_EXTENSIONS = COPILOT_ALLOWED_EXTENSIONS;
const MAX_KB_FILE_BYTES = MAX_COPILOT_FILE_BYTES;

@Component({
  selector: 'app-admin-ai-assistant',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule, AgentQuestionnaireComponent, ChatFormattedTextPipe],
  templateUrl: './admin-ai-assistant.component.html',
  styleUrl: './admin-ai-assistant.component.scss',
  animations: [
    trigger('fadeIn', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(10px)' }),
        animate('300ms ease-out', style({ opacity: 1, transform: 'translateY(0)' })),
      ]),
    ]),
  ],
})
export class AdminAiAssistantComponent implements OnInit {
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;
  @ViewChild('chatBody') chatBody?: ElementRef<HTMLElement>;

  readonly loading = signal(true);
  readonly sending = signal(false);
  readonly uploadingKb = signal(false);
  readonly pendingAttachment = signal<PendingCopilotFile | null>(null);
  readonly overview = signal<AiAssistantOverview | null>(null);
  readonly aiReply = signal<string | null>(null);
  readonly aiError = signal<string | null>(null);
  readonly chatMessages = signal<CopilotChatMessage[]>([]);
  readonly approving = signal(false);
  readonly exportExecuting = signal(false);
  readonly agentMode = signal(false);
  private chatId = 0;

  readonly brainAsset = 'assets/admin/ai-brain.png?v=6';
  readonly brainAssetWebp = 'assets/admin/ai-brain.webp?v=1';
  readonly quickActionCards = QUICK_ACTION_CARDS;
  readonly holoParticles = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

  readonly conversationItems = computed(() => this.buildConversationRows());
  readonly inChatMode = computed(() => this.chatMessages().length > 0 || this.sending());
  readonly canSend = computed(() => {
    const hasText = Boolean(this.prompt.trim());
    const hasFile = Boolean(this.pendingAttachment());
    return (hasText || hasFile) && !this.sending() && !this.uploadingKb();
  });

  readonly fileIcon = copilotFileIcon;

  prompt = '';

  constructor(
    private readonly api: AdminAiService,
    private readonly kbApi: GptKnowledgeService,
    private readonly missionsApi: AgentMissionsService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.loadOverview();
  }

  loadOverview(): void {
    this.loading.set(true);
    this.api.getOverview().subscribe({
      next: (data) => {
        this.overview.set(data);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.toast('Impossible de charger AI Assistant.', 'error');
      },
    });
  }

  sendPrompt(text?: string): void {
    const message = (text ?? this.prompt).trim();
    const pending = this.pendingAttachment();
    if ((!message && !pending) || this.sending() || this.uploadingKb()) return;

    if (!pending && message && this.looksLikeFileReference(message)) {
      const err =
        'Aucun fichier joint. Cliquez sur le trombone pour attacher votre Excel, PDF, Word ou image, puis envoyez votre message.';
      this.aiError.set(err);
      this.toast(err, 'error');
      return;
    }

    const attachmentDisplay = pending ? this.toAttachmentDisplay(pending) : undefined;
    const userMsg: CopilotChatMessage = {
      id: ++this.chatId,
      role: 'admin',
      content: message || `Fichier joint : ${pending?.name ?? ''}`,
      createdAt: new Date(),
      attachment: attachmentDisplay,
    };
    this.chatMessages.update((rows) => [...rows, userMsg]);
    this.scrollChatToBottom();

    this.sending.set(true);
    this.aiError.set(null);
    this.aiReply.set(null);
    this.prompt = '';

    if (pending && pending.kind !== 'image') {
      this.uploadingKb.set(true);
      this.kbApi.upload(pending.file, 'fedex-admin-ops', 'fr').subscribe({
        next: () => {
          this.uploadingKb.set(false);
          this.clearPendingAttachment();
          const queryText =
            message ||
            `Lis attentivement le fichier « ${pending.name} » et extrais toutes les informations pertinentes.`;
          this.runCopilotQuery(queryText, { attachedDocumentName: pending.name });
        },
        error: (err: HttpErrorResponse) => {
          this.uploadingKb.set(false);
          this.sending.set(false);
          const msg = typeof err.error?.detail === 'string' ? err.error.detail : 'Échec indexation du fichier.';
          this.aiError.set(msg);
          this.toast(msg, 'error');
        },
      });
      return;
    }

    if (pending?.kind === 'image' && pending.imageBase64) {
      this.kbApi.upload(pending.file, 'fedex-admin-ops', 'fr').subscribe({ error: () => undefined });
      this.runCopilotQuery(message || 'Décris et analyse cette image en détail.', {
        imageBase64: pending.imageBase64,
        imageMimeType: pending.mimeType,
        attachedDocumentName: pending.name,
      });
      this.clearPendingAttachment();
      return;
    }

    this.runCopilotQuery(message);
  }

  private runCopilotQuery(
    message: string,
    extras?: {
      imageBase64?: string;
      imageMimeType?: string;
      attachedDocumentName?: string;
    },
  ): void {
    const quick = this.resolveQuickAction(message);
    const history = this.buildCopilotHistory();
    this.api
      .query(message, quick, this.agentMode(), history, {
        imageBase64: extras?.imageBase64 ?? null,
        imageMimeType: extras?.imageMimeType ?? null,
        attachedDocumentName: extras?.attachedDocumentName ?? null,
      })
      .subscribe({
        next: (res) => this.handleCopilotResponse(res),
        error: (err: unknown) => {
          this.sending.set(false);
          const httpErr = err instanceof HttpErrorResponse ? err : null;
          const errName = err instanceof Error ? err.name : '';
          const errMessage = err instanceof Error ? err.message : '';
          const isTimeout =
            errName === 'TimeoutError' ||
            errMessage.includes('Timeout') ||
            httpErr?.status === 0;
          const msg = isTimeout
            ? "Délai dépassé (120 s). Jarvis met trop de temps à répondre — réessayez."
            : typeof httpErr?.error?.detail === 'string'
              ? httpErr.error.detail
              : 'Jarvis indisponible.';
          this.aiError.set(msg);
          this.chatMessages.update((rows) => [
            ...rows,
            {
              id: ++this.chatId,
              role: 'agent',
              content: isTimeout
                ? "Je n'ai pas pu terminer l'analyse dans le délai prévu. Réessayez dans quelques secondes."
                : msg,
              createdAt: new Date(),
              agentTypeLabel: 'Jarvis',
              mode: isTimeout ? 'timeout_fallback' : null,
              llmProvider: isTimeout ? 'timeout_fallback' : null,
              confidence: isTimeout ? 0.3 : null,
              error: isTimeout ? 'TIMEOUT' : null,
            },
          ]);
          this.scrollChatToBottom();
          this.toast(msg, 'error');
        },
      });
  }

  private handleCopilotResponse(res: import('../../../../core/services/admin-ai.service').AiAssistantQueryResponse): void {
    this.sending.set(false);
    this.aiReply.set(res.reply);
    if (res.copilot_state) {
      this.api.setCopilotState(res.copilot_state);
    }
    this.chatMessages.update((rows) => [
      ...rows,
      {
        id: ++this.chatId,
        role: 'agent',
        content: res.answer ?? res.reply,
        createdAt: new Date(),
        agentTypeLabel: res.agent_type_label ?? undefined,
        analysisOnly: res.analysis_only ?? false,
        agentSteps: res.agent_steps,
        agentReasoning: res.agent_reasoning ?? null,
        actionExecuted: res.action_executed || !!res.export_download,
        needsApproval: res.needs_approval,
        approvalId: res.approval_id,
        missionId: res.mission_id,
        exportDownload: res.export_download ?? null,
        agentQuestionnaire: res.agent_questionnaire ?? null,
        llmDegraded: res.llm_degraded,
        llmProvider: res.mode ?? res.llm_provider ?? null,
        gptSlug: res.gpt_slug ?? null,
        knowledgeHits: res.knowledge_hits ?? 0,
        toolsUsed: res.tools_used ?? [],
        mode: res.mode ?? null,
        confidence: res.confidence ?? null,
        reasoningSummary: res.reasoning_summary ?? null,
        error: res.error ?? null,
        language: res.language ?? null,
        executionTimeMs: res.execution_time_ms ?? null,
        sourcesUsed: res.sources_used ?? [],
        requiresConfirmation: res.requires_confirmation ?? false,
        suggestedAction: res.suggested_action ?? null,
        exportPreview: res.export_preview ?? null,
        exportStatus: (res.export_status as CopilotChatMessage['exportStatus']) ?? null,
        exportProgressStep: 0,
        exportResult: res.export_result ?? null,
      },
    ]);
    this.scrollChatToBottom();
    if (res.needs_approval) {
      this.toast('Action sensible — approbation requise.', 'success');
    } else if (res.export_download) {
      const fmt = res.export_download.format ?? 'pdf';
      this.toast(
        fmt === 'xlsx' ? 'Excel généré — cliquez sur le lien pour télécharger.' : 'PDF généré — cliquez sur le lien pour télécharger.',
        'success',
      );
    } else if (res.agent_questionnaire) {
      this.toast('L\'agent a besoin d\'une précision.', 'success');
    } else if (res.action_executed) {
      this.toast('Action exécutée.', 'success');
    } else if (res.error) {
      this.toast('Réponse en mode secours — vérifiez le bandeau sous le message.', 'error');
    }
    this.loadOverview();
  }

  approveCopilot(approvalId: number): void {
    if (this.approving()) return;
    this.approving.set(true);
    this.missionsApi.approveAction(approvalId).subscribe({
      next: () => {
        this.approving.set(false);
        this.toast('Action approuvée et exécutée.', 'success');
        this.loadOverview();
      },
      error: (err: HttpErrorResponse) => {
        this.approving.set(false);
        this.toast(err.error?.detail || 'Approbation impossible.', 'error');
      },
    });
  }

  onAgentAnswers(answers: Record<string, string>): void {
    const parts = Object.entries(answers)
      .map(([key, value]) => `${key}: ${value}`)
      .join(' — ');
    this.sendPrompt(`Réponse à la clarification agent : ${parts}`);
  }

  confirmExport(msg: CopilotChatMessage): void {
    if (!msg.suggestedAction || this.exportExecuting()) return;
    this.exportExecuting.set(true);
    this.updateMessage(msg.id, { exportStatus: 'in_progress', exportProgressStep: 1 });

    const steps = [1, 2, 3];
    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      stepIdx += 1;
      if (stepIdx < steps.length) {
        this.updateMessage(msg.id, { exportProgressStep: steps[stepIdx] });
      }
    }, 400);

    this.api.executeExport(msg.suggestedAction).subscribe({
      next: (result) => {
        clearInterval(stepTimer);
        this.exportExecuting.set(false);
        if (!result.success) {
          this.updateMessage(msg.id, {
            exportStatus: 'error',
            content: result.error ?? 'Export échoué.',
          });
          this.toast(result.error ?? 'Export échoué.', 'error');
          return;
        }
        this.updateMessage(msg.id, {
          exportStatus: 'completed',
          exportProgressStep: 4,
          exportDownload: result.export_download ?? null,
          exportResult: result,
          requiresConfirmation: false,
          content: result.reply ?? msg.content,
          actionExecuted: true,
        });
        this.toast(`Export prêt — ${result.records ?? 0} enregistrements.`, 'success');
      },
      error: (err: HttpErrorResponse) => {
        clearInterval(stepTimer);
        this.exportExecuting.set(false);
        this.updateMessage(msg.id, { exportStatus: 'error' });
        this.toast(err.error?.detail ?? 'Export impossible.', 'error');
      },
    });
  }

  cancelExport(msg: CopilotChatMessage): void {
    this.updateMessage(msg.id, {
      requiresConfirmation: false,
      exportStatus: 'error',
      content: `${msg.content}\n\n_Export annulé._`,
    });
  }

  private updateMessage(id: number, patch: Partial<CopilotChatMessage>): void {
    this.chatMessages.update((rows) =>
      rows.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    );
  }

  exportProgressLabel(step: number | undefined): string {
    const labels = ['Préparation', 'Analyse', 'Génération', 'Terminé'];
    const idx = Math.max(0, Math.min((step ?? 1) - 1, labels.length - 1));
    return labels[idx] ?? labels[0];
  }

  exportStatusLabel(status: string | null | undefined): string {
    const map: Record<string, string> = {
      pending: 'En attente',
      in_progress: 'En cours',
      completed: 'Terminé',
      error: 'Erreur',
    };
    return map[status ?? ''] ?? status ?? '';
  }

  downloadLogsExport(spec: AdminExportDownloadSpec): void {
    if (spec.preset === 'admin_platform_report') {
      this.api.downloadPlatformReportPdf(spec.hours ?? 24, spec.filename ?? 'platform-report.pdf').subscribe({
        error: () => this.toast('Échec du téléchargement rapport.', 'error'),
      });
      return;
    }
    if (spec.preset === 'admin_tracking') {
      const numbers = spec.tracking_numbers?.trim();
      if (numbers) {
        this.api.downloadTrackingStatusPdf(numbers, spec.filename ?? 'tracking-status.pdf').subscribe({
          error: () => this.toast('Échec du téléchargement PDF tracking.', 'error'),
        });
        return;
      }
      this.api
        .downloadContextPdf(
          spec.preset,
          spec.limit ?? spec.records ?? 10,
          spec.filename ?? 'tracking-export.pdf',
          spec.module,
          spec.export_token,
        )
        .subscribe({ error: () => this.toast('Échec du téléchargement PDF tracking.', 'error') });
      return;
    }
    const contextPresets = new Set([
      'admin_notifications',
      'admin_users',
      'admin_tickets',
      'admin_conversations',
      'admin_generic',
      'admin_security',
    ]);
    if (contextPresets.has(spec.preset)) {
      this.api
        .downloadContextPdf(
          spec.preset,
          spec.limit ?? spec.records ?? 10,
          spec.filename ?? 'export.pdf',
          spec.module,
          spec.export_token,
        )
        .subscribe({ error: () => this.toast('Échec du téléchargement PDF.', 'error') });
      return;
    }
    if (spec.preset !== 'admin_logs') return;
    const hours = spec.hours ?? 24;
    const fmt = spec.format ?? (spec.filename?.endsWith('.xlsx') ? 'xlsx' : spec.filename?.endsWith('.csv') ? 'csv' : 'pdf');
    if (fmt === 'xlsx') {
      this.api.downloadActivityLogsExcel(hours, spec.filename ?? 'activity-logs.xlsx').subscribe({
        error: () => this.toast('Échec du téléchargement Excel.', 'error'),
      });
      return;
    }
    if (fmt === 'csv') {
      this.api.downloadActivityLogsCsv(hours, spec.filename ?? 'activity-logs.csv').subscribe({
        error: () => this.toast('Échec du téléchargement CSV.', 'error'),
      });
      return;
    }
    this.api.downloadActivityLogsPdf(hours, spec.filename ?? 'activity-logs.pdf').subscribe({
      error: () => this.toast('Échec du téléchargement PDF.', 'error'),
    });
  }

  toggleAgentMode(): void {
    this.agentMode.update((on) => !on);
    this.toast(
      this.agentMode()
        ? 'Mode Agent activé — exécution automatique des tâches admin.'
        : 'Mode analyse — consultation des données + conseil (outils lecture activés).',
      'success',
    );
  }

  runQuickCommand(label: string): void {
    this.prompt = label;
    this.sendPrompt(label);
  }

  rerunConversation(item: ConversationRow): void {
    this.prompt = item.question;
    this.sendPrompt(item.question);
  }

  clearChat(): void {
    this.prompt = '';
    this.clearPendingAttachment();
    this.aiReply.set(null);
    this.aiError.set(null);
    this.chatMessages.set([]);
    this.api.clearCopilotState();
  }

  /** Historique des messages précédents (hors message courant) pour le contexte copilot. */
  private buildCopilotHistory(): { role: 'user' | 'assistant'; content: string }[] {
    const rows = this.chatMessages();
    const prior = rows.length > 0 ? rows.slice(0, -1) : rows;
    return prior.slice(-12).map((m) => {
      const parts = [m.content?.trim() || ''];
      if (m.attachment?.name) {
        parts.push(`[Fichier joint : ${m.attachment.name}]`);
      }
      return {
        role: m.role === 'admin' ? 'user' as const : 'assistant' as const,
        content: parts.filter(Boolean).join('\n'),
      };
    });
  }

  agentDisplayName(msg: CopilotChatMessage): string {
    if (msg.analysisOnly || !this.agentMode()) {
      return 'Jarvis';
    }
    return msg.agentTypeLabel || 'Jarvis Agent';
  }

  statusBadge(msg: CopilotChatMessage): string | null {
    if (msg.exportDownload) return 'EXPORT';
    if (msg.analysisOnly && !msg.actionExecuted) return null;
    if (msg.actionExecuted) return 'FAIT';
    if (msg.needsApproval) return 'EN ATTENTE';
    if (msg.agentQuestionnaire) return 'QUESTION';
    if (msg.llmDegraded && msg.mode !== 'ollama' && msg.mode !== 'jarvis' && msg.mode !== 'local_fallback') return 'DÉGRADÉ';
    return 'ANALYSE';
  }

  /** Libellé traçabilité moteur — Jarvis / Ollama / repli local. */
  providerTraceLabel(msg: CopilotChatMessage): string | null {
    if (msg.role !== 'agent') return null;
    const mode = (msg.mode || msg.llmProvider || '').toLowerCase();
    const degraded = !!msg.llmDegraded && mode !== 'ollama' && mode !== 'jarvis' && mode !== 'local_fallback' && mode !== 'local';
    if (msg.exportDownload) {
      const fmt = (msg.exportDownload.format || 'pdf').toUpperCase();
      return degraded ? `Export ${fmt} · repli local` : `Export ${fmt} · Jarvis`;
    }
    if (mode === 'timeout_fallback') return 'Timeout';
    if (mode === 'jarvis') return 'Jarvis';
    if (mode === 'gemini') return 'Gemini';
    if (mode === 'gemini_pro') return 'Gemini Pro';
    if (mode === 'ollama') return 'Ollama';
    if (mode === 'local_fallback' || mode === 'local' || mode === 'deterministic') return 'Fallback local';
    if (degraded) return 'Repli dégradé';
    if (mode) return mode;
    return null;
  }

  providerTraceTone(msg: CopilotChatMessage): string {
    if (msg.exportDownload) return 'export';
    const mode = (msg.mode || msg.llmProvider || '').toLowerCase();
    if (mode === 'timeout_fallback') return 'degraded';
    if (mode === 'gemini' || mode === 'gemini_pro') return 'gemini';
    if (mode === 'ollama' || mode === 'jarvis') return 'ollama';
    if (msg.llmDegraded || this.isDegradedProvider(msg.llmProvider)) return 'degraded';
    return 'local';
  }

  providerTraceDetails(msg: CopilotChatMessage): string | null {
    const parts: string[] = [];
    if (msg.confidence != null) {
      parts.push(`confiance ${Math.round(msg.confidence * 100)} %`);
    }
    if (msg.executionTimeMs != null) {
      parts.push(`${Math.round(msg.executionTimeMs)} ms`);
    }
    if (msg.language) parts.push(msg.language.toUpperCase());
    if (msg.toolsUsed?.length) parts.push(msg.toolsUsed.join(', '));
    return parts.length ? parts.join(' · ') : null;
  }

  private isDegradedProvider(provider: string | null | undefined): boolean {
    const p = (provider || '').toLowerCase();
    return p === 'degraded';
  }

  stepDotClass(status: string): string {
    if (status === 'done' || status === 'completed') return 'is-done';
    if (status === 'running') return 'is-running';
    if (status === 'error' || status === 'failed') return 'is-error';
    if (status === 'warning') return 'is-warning';
    return 'is-pending';
  }

  clearAttachment(): void {
    this.clearPendingAttachment();
  }

  onUploadClick(): void {
    if (this.uploadingKb() || this.sending()) return;
    this.fileInput?.nativeElement.click();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file || this.uploadingKb()) return;

    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (!KB_FILE_EXTENSIONS.has(ext)) {
      this.toast('Formats : PDF, Excel, Word, images, TXT, CSV.', 'error');
      return;
    }
    if (file.size > MAX_KB_FILE_BYTES) {
      this.toast('Fichier trop volumineux (max 15 Mo).', 'error');
      return;
    }

    const kind = copilotFileKind(file.name, file.type);
    const base: PendingCopilotFile = {
      file,
      name: file.name,
      kind,
      mimeType: file.type || 'application/octet-stream',
    };

    if (kind === 'image') {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        if (typeof result !== 'string') return;
        const comma = result.indexOf(',');
        const imageBase64 = comma >= 0 ? result.slice(comma + 1) : '';
        if (!imageBase64) {
          this.toast('Image illisible.', 'error');
          return;
        }
        this.clearPendingAttachment();
        this.pendingAttachment.set({
          ...base,
          previewUrl: result,
          imageBase64,
        });
        this.toast(`Image « ${file.name} » prête — ajoutez votre question puis envoyez.`, 'success');
      };
      reader.onerror = () => this.toast('Impossible de lire l\'image.', 'error');
      reader.readAsDataURL(file);
      return;
    }

    this.clearPendingAttachment();
    this.pendingAttachment.set(base);
    this.toast(`« ${file.name} » attaché — écrivez votre consigne puis envoyez.`, 'success');
  }

  private toAttachmentDisplay(pending: PendingCopilotFile): CopilotAttachmentDisplay {
    return {
      name: pending.name,
      kind: pending.kind,
      previewUrl: pending.previewUrl,
      mimeType: pending.mimeType,
    };
  }

  private clearPendingAttachment(): void {
    const current = this.pendingAttachment();
    if (current?.previewUrl?.startsWith('blob:')) {
      URL.revokeObjectURL(current.previewUrl);
    }
    this.pendingAttachment.set(null);
  }

  statusClass(status: string): string {
    const s = (status || 'completed').toLowerCase();
    if (s === 'running' || s === 'pending' || s === 'processing') return 'ai-status--processing';
    return 'ai-status--completed';
  }

  statusLabel(status: string): string {
    const s = (status || 'completed').toLowerCase();
    if (s === 'running' || s === 'pending' || s === 'processing') return 'Processing';
    return 'Completed';
  }

  isProcessing(status: string): boolean {
    const s = (status || '').toLowerCase();
    return s === 'processing' || s === 'running' || s === 'pending';
  }

  private buildConversationRows(): ConversationRow[] {
    const api = this.overview()?.recent_conversations ?? [];
    if (api.length === 0 && !this.loading()) {
      return DEMO_CONVERSATIONS;
    }
    return api.map((c) => ({
      id: c.id,
      question: c.question,
      status: c.status,
      created_at: c.created_at,
      relative: this.relativeTime(c.created_at),
    }));
  }

  private relativeTime(iso: string): string {
    if (!iso) return '';
    const diff = Math.max(0, Date.now() - new Date(iso).getTime());
    const min = Math.floor(diff / 60000);
    if (min < 1) return 'Just now';
    if (min < 60) return `${min} min ago`;
    const h = Math.floor(min / 60);
    if (h < 24) return h === 1 ? '1 hour ago' : `${h} hours ago`;
    const d = Math.floor(h / 24);
    return d === 1 ? '1 day ago' : `${d} days ago`;
  }

  private resolveQuickAction(message: string): string | undefined {
    const key = message.trim().toLowerCase();
    if (QUICK_ACTION_MAP[key]) return QUICK_ACTION_MAP[key];
    for (const [label, action] of Object.entries(QUICK_ACTION_MAP)) {
      if (key.includes(label) || label.includes(key)) return action;
    }
    return undefined;
  }

  private looksLikeFileReference(message: string): boolean {
    if (this.looksLikeExportFormatRequest(message)) {
      return false;
    }
    const lower = message.toLowerCase();
    return /\b(excel|xlsx|xls|fichier|document|word|docx|image|photo|capture|tableur)\b/u.test(
      lower,
    ) || (/\bpdf\b/u.test(lower) && !this.recentChatMentionsLogs());
  }

  private looksLikeExportFormatRequest(message: string): boolean {
    const lower = message.toLowerCase();
    if (!/\b(pdf|excel|xlsx|xls|csv)\b/u.test(lower)) {
      return false;
    }
    if (
      /\b(format|forme|export|exporter|générer|generer|télécharger|telecharger|sous)\b/u.test(
        lower,
      )
    ) {
      return true;
    }
    if (/\b(donne|donne-moi|envoie|envoyer|les|en)\b/u.test(lower)) {
      return true;
    }
    return this.recentChatMentionsLogs();
  }

  private recentChatMentionsLogs(): boolean {
    const blob = this.chatMessages()
      .slice(-8)
      .map((m) => m.content)
      .join(' ')
      .toLowerCase();
    return /\b(logs?|journaux|activité|activite|analyze_logs|journal d'activité)\b/u.test(blob);
  }

  private scrollChatToBottom(): void {
    queueMicrotask(() => {
      const el = this.chatBody?.nativeElement;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    });
  }

  private toast(msg: string, type: 'success' | 'error'): void {
    this.snack.open(msg, 'Fermer', {
      duration: 4500,
      panelClass: type === 'success' ? 'set-snack--ok' : 'set-snack--err',
      horizontalPosition: 'end',
      verticalPosition: 'top',
    });
  }
}
