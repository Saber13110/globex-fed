import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild, computed, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import {
  AgentWindowChatResponse,
  AgentWindowHistoryMessage,
  AgentWindowService,
} from '../../../../core/services/agent-window.service';
import { AdminAiService, AdminExportDownloadSpec } from '../../../../core/services/admin-ai.service';
import { ShipmentSummary } from '../../../../core/services/chatbot.service';
import { HistoryService } from '../../../../core/services/history.service';
import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
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

interface ChatRow {
  id: number;
  role: 'admin' | 'jarvis' | 'system';
  content: string;
  latencyMs?: number | null;
  shipment?: ShipmentSummary | null;
  exportDownload?: AdminExportDownloadSpec | null;
}

@Component({
  selector: 'app-admin-agent-window',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe, ChatFormattedTextPipe, ShipmentCardComponent],
  templateUrl: './admin-agent-window.component.html',
  styleUrl: './admin-agent-window.component.scss',
})
export class AdminAgentWindowComponent implements OnInit {
  private readonly api = inject(AgentWindowService);
  private readonly adminAi = inject(AdminAiService);
  private readonly history = inject(HistoryService);
  private readonly i18n = inject(I18nService);
  private chatId = 0;

  readonly openCopilot = output<string>();

  @ViewChild('threadEl') threadEl?: ElementRef<HTMLElement>;
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;

  readonly prompt = signal('');
  readonly attachment = signal<AdminChatAttachment | null>(null);
  readonly chatSessionId = signal<number | null>(null);
  readonly sending = signal(false);
  readonly error = signal<string | null>(null);
  readonly sessionId = signal<string | null>(null);
  readonly messages = signal<ChatRow[]>([]);
  readonly jarvisOnline = signal<boolean | null>(null);
  readonly jarvisEnabled = signal(true);
  readonly jarvisLatency = signal<number | null>(null);
  readonly lastEngine = signal<string | null>(null);

  readonly canSend = computed(() => {
    return (!!this.prompt().trim() || !!this.attachment()) && !this.sending() && this.jarvisOnline() !== false;
  });

  ngOnInit(): void {
    this.chatSessionId.set(readPersistedAdminChatSessionId());
    this.refreshHealth();
  }

  refreshHealth(): void {
    this.api.health().subscribe({
      next: (h) => {
        this.jarvisEnabled.set(h.enabled);
        this.jarvisOnline.set(h.online);
        this.jarvisLatency.set(h.latency_ms ?? null);
      },
      error: () => {
        this.jarvisOnline.set(false);
      },
    });
  }

  send(): void {
    const text = this.prompt().trim();
    const att = this.attachment();
    if ((!text && !att) || this.sending()) return;

    const displayContent = att ? `${text ? text + '\n' : ''}📎 ${att.name}` : text;
    this.messages.update((rows) => [
      ...rows,
      { id: ++this.chatId, role: 'admin', content: displayContent },
    ]);
    this.prompt.set('');
    this.removeAttachment();
    this.sending.set(true);
    this.error.set(null);
    this.scrollThread();

    const history: AgentWindowHistoryMessage[] = this.messages()
      .filter((m) => m.role === 'admin' || m.role === 'jarvis')
      .slice(-10)
      .map((m) => ({
        role: m.role === 'admin' ? 'user' : 'assistant',
        content: m.content,
      }));

    this.api
      .chat({
        message: text,
        session_id: this.sessionId(),
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
              : 'Jarvis indisponible — vérifiez qu\'il tourne sur le port 8010.';
          this.error.set(detail);
          this.sending.set(false);
          this.jarvisOnline.set(false);
        },
      });
  }

  newConversation(): void {
    this.sessionId.set(null);
    this.chatSessionId.set(null);
    clearPersistedAdminChatSessionId();
    this.messages.set([]);
    this.error.set(null);
    this.lastEngine.set(null);
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

  downloadExport(spec: AdminExportDownloadSpec): void {
    downloadAdminExport(this.adminAi, spec, (msg) => this.error.set(msg), {
      history: this.history,
      lang: this.i18n.toBackendCode() as 'fr' | 'en' | 'ar',
    });
  }

  goToCopilot(hint?: string | null): void {
    this.openCopilot.emit(hint || '');
  }

  onEnter(event: Event): void {
    const ke = event as KeyboardEvent;
    if (ke.shiftKey) return;
    event.preventDefault();
    this.send();
  }

  private onReply(res: AgentWindowChatResponse): void {
    this.sessionId.set(res.session_id);
    if (res.chat_session_id != null) {
      this.chatSessionId.set(res.chat_session_id);
      persistAdminChatSessionId(res.chat_session_id);
    }
    this.lastEngine.set(res.engine ?? 'jarvis');
    this.messages.update((rows) => [
      ...rows,
      {
        id: ++this.chatId,
        role: res.redirect_to_copilot ? 'system' : 'jarvis',
        content: res.reply,
        latencyMs: res.latency_ms,
        shipment: res.shipment ?? null,
        exportDownload: res.export_download ?? null,
      },
    ]);
    this.sending.set(false);
    this.scrollThread();
  }

  showShipmentCard(shipment: ShipmentSummary | null | undefined): boolean {
    return shouldShowShipmentCardInChat(shipment);
  }

  private scrollThread(): void {
    setTimeout(() => {
      const el = this.threadEl?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }
}
