import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AuthService } from '../../../../core/services/auth.service';
import {
  EmployeeAiAction,
  EmployeeAiAgentCard,
  EmployeeAiAgentConversationDetail,
  EmployeeAiAgentConversationSummary,
  EmployeeAiAgentLiveContext,
  EmployeeAiAgentMessage,
  EmployeeAiAgentMessageResponse,
  EmployeePortalService,
} from '../../../../core/services/employee-portal.service';
import { SupportService } from '../../../../core/services/support.service';

interface AgentAttachment {
  localId: string;
  name: string;
  url: string;
  uploading?: boolean;
}

interface AgentMessageAttachment {
  name: string;
  url: string;
}

interface AgentMessage {
  role: 'user' | 'assistant';
  text: string;
  intent?: string;
  cards?: EmployeeAiAgentCard[];
  actions?: EmployeeAiAction[];
  html?: SafeHtml;
  attachments?: AgentMessageAttachment[];
}

interface QuickAction {
  icon: string;
  titleKey: string;
  descKey: string;
  promptKey: string;
}

@Component({
  selector: 'app-employee-ai-agent-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-ai-agent-page.component.html',
  styleUrl: './employee-ai-agent-page.component.scss',
})
export class EmployeeAiAgentPageComponent implements OnInit, OnDestroy {
  @ViewChild('threadEl') threadEl?: ElementRef<HTMLElement>;
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;

  readonly heroBanner = 'assets/employee/hero-ai-agent-v1.png?v=3';
  readonly attachmentAccept = '.pdf,.png,.jpg,.jpeg,.webp,.gif,.doc,.docx,.xls,.xlsx,.csv,.txt,.zip';

  messages: AgentMessage[] = [];
  conversations: EmployeeAiAgentConversationSummary[] = [];
  conversationId: string | null = null;
  historyQuery = '';
  draft = '';
  loading = false;
  conversationsLoading = true;
  errorToast = '';
  accountName = '';
  employeeInitials = 'EM';
  liveContext: EmployeeAiAgentLiveContext | null = null;
  contextLoading = true;
  contextTab: 'clients' | 'shipments' | 'tickets' | 'documents' = 'clients';
  pendingAttachments: AgentAttachment[] = [];
  voiceSupported = false;
  voiceListening = false;

  private recognition: any = null;
  private toastTimer?: ReturnType<typeof setTimeout>;

  readonly contextTabs = [
    { id: 'clients' as const, labelKey: 'employee.copilot.ctxClients' },
    { id: 'shipments' as const, labelKey: 'employee.copilot.ctxShipments' },
    { id: 'tickets' as const, labelKey: 'employee.copilot.ctxTickets' },
    { id: 'documents' as const, labelKey: 'employee.copilot.ctxDocuments' },
  ];

  readonly quickActions: QuickAction[] = [
    { icon: 'package', titleKey: 'employee.copilot.actionTracking', descKey: 'employee.copilot.actionTrackingDesc', promptKey: 'employee.copilot.promptTracking' },
    { icon: 'users', titleKey: 'employee.copilot.actionClient', descKey: 'employee.copilot.actionClientDesc', promptKey: 'employee.copilot.promptClient' },
    { icon: 'ticket', titleKey: 'employee.copilot.actionTickets', descKey: 'employee.copilot.actionTicketsDesc', promptKey: 'employee.copilot.promptTickets' },
    { icon: 'file', titleKey: 'employee.agent.actionPendingDocs', descKey: 'employee.agent.actionPendingDocsDesc', promptKey: 'employee.copilot.promptDocs' },
    { icon: 'alert', titleKey: 'employee.copilot.actionExceptions', descKey: 'employee.copilot.actionExceptionsDesc', promptKey: 'employee.copilot.promptExceptions' },
    { icon: 'reply', titleKey: 'employee.agent.actionReply', descKey: 'employee.agent.actionReplyDesc', promptKey: 'employee.agent.promptReply' },
  ];

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly support: SupportService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly auth: AuthService,
    private readonly i18n: I18nService,
    private readonly sanitizer: DomSanitizer,
  ) {}

  ngOnInit(): void {
    this.initVoiceRecognition();
    this.auth.me().subscribe({
      next: (p) => {
        this.accountName = p.full_name;
        this.employeeInitials = this.initials(p.full_name);
      },
    });
    this.loadConversations();
    this.loadContext();
    const q = this.route.snapshot.queryParamMap.get('q');
    if (q) {
      this.draft = q;
      void this.bootstrapAndSend();
    }
  }

  ngOnDestroy(): void {
    if (this.recognition && this.voiceListening) {
      this.recognition.stop();
    }
    if (this.toastTimer) clearTimeout(this.toastTimer);
  }

  get canSend(): boolean {
    const readyAttachments = this.pendingAttachments.filter((a) => a.url && !a.uploading);
    const uploading = this.pendingAttachments.some((a) => a.uploading);
    return !this.loading && !uploading && (!!this.draft.trim() || readyAttachments.length > 0);
  }

  loadConversations(): void {
    this.conversationsLoading = true;
    this.employee.listAiAgentConversations(this.historyQuery).subscribe({
      next: (rows) => {
        this.conversations = rows;
        this.conversationsLoading = false;
      },
      error: () => (this.conversationsLoading = false),
    });
  }

  loadContext(): void {
    this.contextLoading = true;
    this.employee.getAiAgentLiveContext().subscribe({
      next: (ctx) => {
        this.liveContext = ctx;
        this.contextLoading = false;
      },
      error: () => (this.contextLoading = false),
    });
  }

  newChat(): void {
    this.employee.createAiAgentConversation().subscribe({
      next: (conv) => {
        this.conversationId = conv.id;
        this.messages = [];
        this.loadConversations();
      },
    });
  }

  selectConversation(id: string): void {
    this.conversationId = id;
    this.employee.getAiAgentConversation(id).subscribe({
      next: (conv) => {
        this.messages = conv.messages.map((m) => this.mapApiMessage(m));
        this.scrollThread();
      },
    });
  }

  deleteConversation(id: string, event: Event): void {
    event.stopPropagation();
    this.employee.deleteAiAgentConversation(id).subscribe({
      next: () => {
        if (this.conversationId === id) {
          this.conversationId = null;
          this.messages = [];
        }
        this.loadConversations();
      },
    });
  }

  runQuickAction(action: QuickAction): void {
    this.draft = this.i18n.t(action.promptKey);
    void this.bootstrapAndSend();
  }

  get conversationGroups(): { label: string; items: EmployeeAiAgentConversationSummary[] }[] {
    const order = ['Today', 'Yesterday', 'Last Week', 'Older'];
    const map = new Map<string, EmployeeAiAgentConversationSummary[]>();
    for (const c of this.conversations) {
      const g = c.group || 'Older';
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(c);
    }
    const groups: { label: string; items: EmployeeAiAgentConversationSummary[] }[] = [];
    for (const label of order) {
      if (map.has(label)) groups.push({ label, items: map.get(label)! });
    }
    for (const [label, items] of map) {
      if (!order.includes(label)) groups.push({ label, items });
    }
    return groups;
  }

  formatTime(iso: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (this.canSend) void this.bootstrapAndSend();
    }
  }

  triggerAttachment(): void {
    this.fileInput?.nativeElement.click();
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (!files?.length) return;

    Array.from(files).forEach((file) => {
      const err = this.support.validateAttachmentFile(file);
      if (err === 'type') {
        this.showToast(this.i18n.t('support.attachmentTypeError'));
        return;
      }
      if (err === 'size') {
        this.showToast(this.i18n.t('support.attachmentSizeError'));
        return;
      }

      const item: AgentAttachment = {
        localId: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        name: file.name,
        url: '',
        uploading: true,
      };
      this.pendingAttachments.push(item);
      const index = this.pendingAttachments.length - 1;

      this.support.uploadAttachment(file).subscribe({
        next: (res) => {
          this.pendingAttachments[index] = {
            localId: item.localId,
            name: res.filename || file.name,
            url: res.url,
          };
        },
        error: () => {
          this.pendingAttachments.splice(index, 1);
          this.showToast(this.i18n.t('support.attachmentUploadError'));
        },
      });
    });

    input.value = '';
  }

  removeAttachment(index: number): void {
    this.pendingAttachments.splice(index, 1);
  }

  openAttachment(url: string, event: Event): void {
    event.preventDefault();
    this.support.openAttachment(url).subscribe({
      error: () => this.showToast(this.i18n.t('support.attachmentOpenError')),
    });
  }

  toggleVoice(): void {
    if (!this.voiceSupported || !this.recognition) {
      this.showToast(this.i18n.t('employee.agent.voiceUnsupported'));
      return;
    }
    if (this.voiceListening) {
      this.recognition.stop();
      this.voiceListening = false;
      return;
    }
    try {
      this.voiceListening = true;
      this.recognition.start();
    } catch {
      this.voiceListening = false;
      this.showToast(this.i18n.t('employee.agent.voiceUnsupported'));
    }
  }

  async bootstrapAndSend(): Promise<void> {
    if (!this.conversationId) {
      await new Promise<void>((resolve) => {
        this.employee.createAiAgentConversation().subscribe({
          next: (conv) => {
            this.conversationId = conv.id;
            resolve();
          },
          error: () => resolve(),
        });
      });
    }
    this.send();
  }

  send(): void {
    const text = this.draft.trim();
    const readyAttachments = this.pendingAttachments.filter((a) => a.url && !a.uploading);
    if ((!text && !readyAttachments.length) || this.loading || !this.conversationId) return;

    if (this.voiceListening && this.recognition) {
      this.recognition.stop();
      this.voiceListening = false;
    }

    const attachmentNote = readyAttachments.length
      ? `\n\n[${this.i18n.t('employee.assistant.attachmentLabel')}: ${readyAttachments.map((a) => a.name).join(', ')}]`
      : '';
    const attachmentUrls = readyAttachments.length
      ? `\n${readyAttachments.map((a) => `- ${a.name}: ${a.url}`).join('\n')}`
      : '';
    const userText = (text || this.i18n.t('employee.assistant.attachmentOnly')) + attachmentNote + attachmentUrls;

    this.messages.push({
      role: 'user',
      text: userText,
      attachments: readyAttachments.map((a) => ({ name: a.name, url: a.url })),
    });
    this.draft = '';
    this.pendingAttachments = [];
    this.loading = true;
    this.scrollThread();

    this.employee.sendAiAgentMessage(userText, this.conversationId).subscribe({
      next: (res) => this.pushAssistant(res),
      error: () => {
        this.messages.push({
          role: 'assistant',
          text: this.i18n.t('employee.copilot.error'),
          html: this.formatMarkdown(this.i18n.t('employee.copilot.error')),
        });
        this.loading = false;
        this.scrollThread();
        this.showToast(this.i18n.t('employee.copilot.error'));
      },
    });
  }

  private initVoiceRecognition(): void {
    const w = window as any;
    const SpeechRecognitionCtor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) return;

    this.voiceSupported = true;
    this.recognition = new SpeechRecognitionCtor();
    this.recognition.lang = document.documentElement.lang || 'fr-FR';
    this.recognition.interimResults = true;
    this.recognition.continuous = false;

    this.recognition.onresult = (event: any) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0]?.transcript ?? '';
      }
      this.draft = `${this.draft} ${transcript}`.trim();
    };

    this.recognition.onend = () => {
      this.voiceListening = false;
    };

    this.recognition.onerror = () => {
      this.voiceListening = false;
    };
  }

  private showToast(message: string): void {
    this.errorToast = message;
    if (this.toastTimer) clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => {
      this.errorToast = '';
    }, 4200);
  }

  sendAdminDraft(draft: string): void {
    void this.router.navigate(['/employee/admin-chat'], { queryParams: { draft } });
  }

  cardTypeLabel(type: string): string {
    const map: Record<string, string> = {
      client: 'employee.copilot.cardClient',
      shipment: 'employee.copilot.cardShipment',
      ticket: 'employee.copilot.cardTicket',
      document: 'employee.copilot.cardDocument',
      admin_draft: 'employee.copilot.adminDraft',
    };
    return map[type] ?? 'employee.copilot.cardResult';
  }

  routePath(route: string): string {
    return route.split('?')[0];
  }

  routeQuery(route: string): Record<string, string> | null {
    const idx = route.indexOf('?');
    if (idx < 0) return null;
    const params = new URLSearchParams(route.slice(idx + 1));
    const query: Record<string, string> = {};
    params.forEach((value, key) => {
      query[key] = value;
    });
    return Object.keys(query).length ? query : null;
  }

  formatMarkdown(text: string): SafeHtml {
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/\n/g, '<br/>');
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  private mapApiMessage(m: EmployeeAiAgentMessage): AgentMessage {
    return {
      role: m.role as 'user' | 'assistant',
      text: m.content,
      intent: m.intent,
      cards: m.cards,
      html: m.role === 'assistant' ? this.formatMarkdown(m.content) : undefined,
    };
  }

  private pushAssistant(res: EmployeeAiAgentMessageResponse): void {
    this.conversationId = res.conversationId;
    this.messages.push({
      role: 'assistant',
      text: res.reply,
      intent: res.intent,
      cards: res.cards,
      actions: res.actions,
      html: this.formatMarkdown(res.reply),
    });
    this.loading = false;
    this.loadConversations();
    this.loadContext();
    this.scrollThread();
  }

  private scrollThread(): void {
    setTimeout(() => {
      const el = this.threadEl?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }

  private initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'EM';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
}
