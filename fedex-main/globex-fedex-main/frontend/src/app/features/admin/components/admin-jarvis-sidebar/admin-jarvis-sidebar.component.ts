import { CommonModule } from '@angular/common';
import {
  Component,
  ElementRef,
  Input,
  OnChanges,
  OnInit,
  SimpleChanges,
  ViewChild,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { AdminAiService, AdminExportDownloadSpec } from '../../../../core/services/admin-ai.service';
import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import {
  JarvisAdminService,
  JarvisAgentStep,
  JarvisHistoryMessage,
} from '../../../../core/services/jarvis-admin.service';
import { ShipmentSummary } from '../../../../core/services/chatbot.service';
import { HistoryService } from '../../../../core/services/history.service';
import { ChatFormattedTextPipe } from '../../../../shared/pipes/chat-formatted-text.pipe';
import { ShipmentCardComponent } from '../../../../shared/components/shipment-card/shipment-card.component';
import { shouldShowShipmentCardInChat } from '../../../../shared/utils/shipment-card.util';
import { downloadAdminExport } from '../../utils/admin-export-download.helper';
import {
  AdminChatAttachment,
  attachmentFromClipboardItems,
  readAttachmentFile,
} from '../../utils/admin-chat-attachment.util';
import {
  clearPersistedAdminChatSessionId,
  persistAdminChatSessionId,
  readPersistedAdminChatSessionId,
} from '../../utils/admin-chat-session.util';

/** Prompt injecté depuis l'overlay Accompagnement (mode Accompagnement). */
export interface JarvisInjectedPrompt {
  id: number;
  text: string;
  image?: { base64: string; mime: string; name: string } | null;
  autosend?: boolean;
}

export interface JarvisSidebarMessage {
  id: number;
  role: 'admin' | 'jarvis' | 'system';
  content: string;
  executionTimeMs?: number | null;
  agentSteps?: JarvisAgentStep[];
  needsApproval?: boolean;
  approvalId?: number | null;
  exportDownload?: AdminExportDownloadSpec | null;
  toolsUsed?: string[];
  shipment?: ShipmentSummary | null;
}

const JARVIS_MARK = 'assets/admin/jarvis-mark.png';
const STORAGE_KEY = 'globex_admin_jarvis_drawer';

@Component({
  selector: 'app-admin-jarvis-sidebar',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe, ChatFormattedTextPipe, ShipmentCardComponent],
  templateUrl: './admin-jarvis-sidebar.component.html',
  styleUrl: './admin-jarvis-sidebar.component.scss',
})
export class AdminJarvisSidebarComponent implements OnInit, OnChanges {
  private readonly jarvis = inject(JarvisAdminService);
  private readonly adminAi = inject(AdminAiService);
  private readonly history = inject(HistoryService);
  private readonly i18n = inject(I18nService);
  private chatId = 0;

  @Input() adminName = 'Admin';
  /** Prompt/capture poussé par l'overlay Accompagnement (via AdminPageComponent). */
  @Input() pendingPrompt: JarvisInjectedPrompt | null = null;
  private lastInjectedId = 0;
  readonly jarvisMarkSrc = JARVIS_MARK;

  readonly closeDrawer = output<void>();
  readonly expandWindow = output<void>();

  @ViewChild('threadEl') threadEl?: ElementRef<HTMLElement>;
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;

  readonly prompt = signal('');
  readonly attachment = signal<AdminChatAttachment | null>(null);
  readonly chatSessionId = signal<number | null>(null);
  readonly sending = signal(false);
  readonly approving = signal(false);
  readonly error = signal<string | null>(null);
  readonly messages = signal<JarvisSidebarMessage[]>([]);
  readonly agentEnabled = signal(true);
  readonly ollamaReady = signal<boolean | null>(null);
  readonly healthDetail = signal<string | null>(null);

  readonly canSend = computed(
    () => (!!this.prompt().trim() || !!this.attachment()) && !this.sending() && this.agentEnabled(),
  );

  readonly suggestionChips = computed(() => {
    this.i18n.lang();
    return [
      this.i18n.t('admin.jarvis.sidebar.chip1'),
      this.i18n.t('admin.jarvis.sidebar.chip2'),
      this.i18n.t('admin.jarvis.sidebar.chip3'),
    ];
  });

  ngOnInit(): void {
    this.chatSessionId.set(readPersistedAdminChatSessionId());
    this.refreshHealth();
    // Si un prompt a déjà été poussé avant le montage de la sidebar.
    this.applyInjectedPrompt();
  }

  ngOnChanges(_changes: SimpleChanges): void {
    this.applyInjectedPrompt();
  }

  /** Applique un prompt/capture injecté par l'overlay Accompagnement (1 seule fois par id). */
  private applyInjectedPrompt(): void {
    const p = this.pendingPrompt;
    if (!p || !p.id || p.id === this.lastInjectedId) return;
    this.lastInjectedId = p.id;
    if (typeof p.text === 'string' && p.text) {
      this.prompt.set(p.text);
    }
    if (p.image && p.image.base64) {
      this.attachment.set({
        base64: p.image.base64,
        mime: p.image.mime || 'image/jpeg',
        name: p.image.name || 'capture.jpg',
        isImage: true,
      });
      this.error.set(null);
    }
    if (p.autosend) {
      // Laisse le change-detection appliquer les signaux avant d'envoyer.
      setTimeout(() => this.send(), 0);
    } else {
      // Met le focus sur le chat pour que l'utilisateur voie la capture collée.
      setTimeout(() => {
        const el = document.querySelector('.jsidebar__input') as HTMLTextAreaElement | null;
        el?.focus();
      }, 60);
    }
  }

  refreshHealth(): void {
    this.jarvis.health().subscribe({
      next: (h) => {
        this.agentEnabled.set(h.enabled);
        const inferenceOk = h.ollama_inference_ok ?? h.ollama_online;
        this.ollamaReady.set(inferenceOk);
        this.healthDetail.set(h.detail ?? h.ollama_model ?? null);
      },
      error: (err: unknown) => {
        const httpErr = err instanceof HttpErrorResponse ? err : null;
        const isTimeout =
          !httpErr ||
          httpErr.status === 0 ||
          httpErr.status === 504 ||
          (err instanceof Error && err.name === 'TimeoutError');
        if (isTimeout) {
          this.ollamaReady.set(false);
          this.healthDetail.set(this.i18n.t('admin.jarvis.sidebar.timeoutHint'));
        } else {
          this.agentEnabled.set(false);
          this.ollamaReady.set(false);
          this.healthDetail.set(null);
        }
      },
    });
  }

  close(): void {
    this.closeDrawer.emit();
  }

  expand(): void {
    this.expandWindow.emit();
  }

  newConversation(): void {
    this.messages.set([]);
    this.error.set(null);
    this.chatSessionId.set(null);
    clearPersistedAdminChatSessionId();
    this.removeAttachment();
  }

  openFilePicker(): void {
    this.fileInput?.nativeElement.click();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    void this.applyAttachmentFile(file);
  }

  onPaste(event: ClipboardEvent): void {
    const items = event.clipboardData?.items;
    if (!items) return;
    const file = attachmentFromClipboardItems(items);
    if (!file) return;
    event.preventDefault();
    void this.applyAttachmentFile(file);
  }

  private async applyAttachmentFile(file: File): Promise<void> {
    const result = await readAttachmentFile(file);
    if (!result.ok) {
      this.error.set(
        this.i18n.t(
          result.error === 'format'
            ? 'admin.jarvis.sidebar.fileFormatError'
            : 'admin.jarvis.sidebar.fileSizeError',
        ),
      );
      return;
    }
    this.attachment.set(result.attachment);
    this.error.set(null);
  }

  removeAttachment(): void {
    this.attachment.set(null);
  }

  useSuggestion(text: string): void {
    this.prompt.set(text);
    this.send();
  }

  onEnter(event: Event): void {
    const ke = event as KeyboardEvent;
    if (ke.shiftKey) return;
    event.preventDefault();
    this.send();
  }

  send(): void {
    const text = this.prompt().trim();
    const att = this.attachment();
    if ((!text && !att) || this.sending()) return;

    const displayContent = att
      ? `${text ? text + '\n' : ''}📎 ${att.name}`
      : text;
    this.messages.update((rows) => [
      ...rows,
      { id: ++this.chatId, role: 'admin', content: displayContent },
    ]);
    this.prompt.set('');
    this.removeAttachment();
    this.sending.set(true);
    this.error.set(null);
    this.scrollThread();

    const history: JarvisHistoryMessage[] = this.messages()
      .filter((m) => m.role === 'admin' || m.role === 'jarvis')
      .slice(-10)
      .map((m) => ({
        role: m.role === 'admin' ? 'user' : 'assistant',
        content: m.content,
      }));

    this.jarvis
      .chat({
        message: text,
        agent_mode: true,
        conversation_history: history.slice(0, -1),
        ui_language: this.i18n.toBackendCode(),
        chat_session_id: this.chatSessionId(),
        image_base64: att?.base64 ?? null,
        image_mime_type: att?.mime ?? null,
        file_name: att?.name ?? null,
      })
      .subscribe({
        next: (res) => this.onReply(res),
        error: (err: HttpErrorResponse) => {
          const detail =
            typeof err.error?.detail === 'string'
              ? err.error.detail
              : this.i18n.t('admin.jarvis.sidebar.offlineHint');
          const detailLow = detail.toLowerCase();
          const isTimeout =
            err.status === 504 ||
            err.status === 0 ||
            detailLow.includes('timeout') ||
            detailLow.includes('cold start') ||
            detailLow.includes('ollama');
          const isAgentDisabled =
            err.status === 503 && detailLow.includes('globex_agent_enabled');

          if (isAgentDisabled) {
            this.agentEnabled.set(false);
          } else if (isTimeout) {
            this.ollamaReady.set(false);
            this.error.set(this.i18n.t('admin.jarvis.sidebar.timeoutHint'));
            this.refreshHealth();
          } else {
            this.error.set(detail);
          }
          this.sending.set(false);
        },
      });
  }

  approve(approvalId: number): void {
    if (this.approving()) return;
    this.approving.set(true);
    this.jarvis.approve(approvalId).subscribe({
      next: (res) => {
        this.approving.set(false);
        if (res.reply) {
          this.messages.update((rows) => [
            ...rows,
            { id: ++this.chatId, role: 'jarvis', content: res.reply! },
          ]);
        }
        this.scrollThread();
      },
      error: (err: HttpErrorResponse) => {
        this.approving.set(false);
        this.error.set(
          typeof err.error?.detail === 'string' ? err.error.detail : 'Approbation impossible.',
        );
      },
    });
  }

  reject(approvalId: number): void {
    if (this.approving()) return;
    this.approving.set(true);
    this.jarvis.reject(approvalId).subscribe({
      next: (res) => {
        this.approving.set(false);
        if (res.reply) {
          this.messages.update((rows) => [
            ...rows,
            { id: ++this.chatId, role: 'system', content: res.reply! },
          ]);
        }
        this.scrollThread();
      },
      error: () => {
        this.approving.set(false);
        this.error.set('Refus impossible.');
      },
    });
  }

  downloadExport(spec: AdminExportDownloadSpec): void {
    downloadAdminExport(this.adminAi, spec, (msg) => this.error.set(msg), {
      history: this.history,
      lang: this.i18n.toBackendCode() as 'fr' | 'en' | 'ar',
    });
  }

  private onReply(res: import('../../../../core/services/jarvis-admin.service').JarvisChatResponse): void {
    this.sending.set(false);
    this.agentEnabled.set(true);
    if (res.chat_session_id != null) {
      this.chatSessionId.set(res.chat_session_id);
      persistAdminChatSessionId(res.chat_session_id);
    }
    if (res.llm_degraded) {
      this.ollamaReady.set(false);
    } else if (res.tools_used?.length && !res.tools_used.includes('greeting') && !res.tools_used.includes('capabilities')) {
      this.ollamaReady.set(true);
    }
    this.messages.update((rows) => [
      ...rows,
      {
        id: ++this.chatId,
        role: 'jarvis',
        content: res.reply,
        executionTimeMs: res.execution_time_ms,
        agentSteps: res.agent_steps,
        needsApproval: res.needs_approval,
        approvalId: res.approval_id,
        exportDownload: res.export_download ?? null,
        toolsUsed: res.tools_used,
        shipment: res.shipment ?? null,
      },
    ]);
    this.scrollThread();
  }

  showShipmentCard(shipment: ShipmentSummary | null | undefined): boolean {
    return shouldShowShipmentCardInChat(shipment);
  }

  private scrollThread(): void {
    setTimeout(() => {
      const el = this.threadEl?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 40);
  }

  static readPersistedOpen(): boolean {
    try {
      return localStorage.getItem(STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  }

  static persistOpen(open: boolean): void {
    try {
      localStorage.setItem(STORAGE_KEY, open ? '1' : '0');
    } catch {
      /* ignore */
    }
  }
}
