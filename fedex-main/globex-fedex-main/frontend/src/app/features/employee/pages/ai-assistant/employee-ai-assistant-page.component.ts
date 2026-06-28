import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AuthService } from '../../../../core/services/auth.service';
import {
  EmployeeAssistantMessage,
  EmployeeAssistantSession,
  EmployeeAiAssistantStateService,
  EmployeeAssistantAttachment,
} from '../../../../core/services/employee-ai-assistant-state.service';
import {
  EmployeeAiTrackingResult,
  EmployeeDashboardWorkspace,
  EmployeePortalService,
} from '../../../../core/services/employee-portal.service';

interface QuickAction {
  labelKey: string;
  descKey: string;
  promptKey: string;
  icon: string;
}

interface OpsMetric {
  labelKey: string;
  value: number;
  route: string;
  icon: string;
  tone?: 'danger' | 'default';
}

interface ActivityItem {
  title: string;
  subtitle: string;
  time: string;
  icon: string;
}

interface TimelineStep {
  labelKey: string;
  done: boolean;
  active: boolean;
}

interface TrackingCardView {
  tracking: EmployeeAiTrackingResult;
  origin: string;
  destination: string;
  lastUpdate: string;
}

@Component({
  selector: 'app-employee-ai-assistant-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-ai-assistant-page.component.html',
  styleUrl: './employee-ai-assistant-page.component.scss',
})
export class EmployeeAiAssistantPageComponent implements OnInit {
  @ViewChild('threadEl') threadEl?: ElementRef<HTMLElement>;
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;

  sessions: EmployeeAssistantSession[] = [];
  activeSession: EmployeeAssistantSession | null = null;
  workspace: EmployeeDashboardWorkspace | null = null;
  draft = '';
  loading = false;
  accountName = '';
  employeeInitials = 'EM';
  pendingAttachments: EmployeeAssistantAttachment[] = [];
  renamingId: string | null = null;
  renameDraft = '';
  historyOpen = true;

  readonly heroIllustration = 'assets/employee/ai-core-hero.png?v=6';

  readonly quickActions: QuickAction[] = [
    { labelKey: 'employee.assistant.quickTracking', descKey: 'employee.assistant.quickTrackingDesc', promptKey: 'employee.assistant.promptTracking', icon: 'package' },
    { labelKey: 'employee.assistant.quickTickets', descKey: 'employee.assistant.quickTicketsDesc', promptKey: 'employee.assistant.promptSupport', icon: 'ticket' },
    { labelKey: 'employee.assistant.quickClient', descKey: 'employee.assistant.quickClientDesc', promptKey: 'employee.assistant.promptClient', icon: 'users' },
    { labelKey: 'employee.assistant.quickDocs', descKey: 'employee.assistant.quickDocsDesc', promptKey: 'employee.assistant.promptDocument', icon: 'file' },
  ];

  constructor(
    private readonly assistantState: EmployeeAiAssistantStateService,
    private readonly employee: EmployeePortalService,
    private readonly route: ActivatedRoute,
    private readonly auth: AuthService,
    private readonly i18n: I18nService,
    private readonly sanitizer: DomSanitizer,
  ) {}

  ngOnInit(): void {
    this.auth.me().subscribe({
      next: (p) => {
        this.accountName = p.full_name;
        this.employeeInitials = this.initials(p.full_name);
      },
    });
    this.employee.getDashboard().subscribe({
      next: (ws) => (this.workspace = ws),
    });
    this.seedDemoIfEmpty();
    this.refreshSessions();
    const q = this.route.snapshot.queryParamMap.get('q');
    if (q) {
      this.ensureActiveSession();
      this.draft = q;
      this.send();
    } else if (!this.activeSession) {
      this.selectFirstOrNew();
    }
  }

  get messages(): EmployeeAssistantMessage[] {
    return this.activeSession?.messages ?? [];
  }

  get opsMetrics(): OpsMetric[] {
    const ws = this.workspace;
    return [
      {
        labelKey: 'employee.assistant.opsShipments',
        value: ws?.tracking_summary.active_count ?? 8,
        route: '/employee/tracking',
        icon: 'package',
      },
      {
        labelKey: 'employee.assistant.opsTickets',
        value: ws?.stats.open_tickets ?? 2,
        route: '/employee/support',
        icon: 'ticket',
      },
      {
        labelKey: 'employee.assistant.opsDocs',
        value: ws?.stats.documents_processed ?? 5,
        route: '/employee/documents',
        icon: 'file',
      },
      {
        labelKey: 'employee.assistant.opsExceptions',
        value: ws?.stats.tracking_exceptions ?? 0,
        route: '/employee/tracking',
        icon: 'alert',
        tone: (ws?.stats.tracking_exceptions ?? 0) > 0 ? 'danger' : 'default',
      },
    ];
  }

  get recentActivity(): ActivityItem[] {
    const ws = this.workspace;
    const items: ActivityItem[] = [];
    for (const ev of (ws?.tracking_summary.latest_events ?? []).slice(0, 2)) {
      items.push({
        title: ev.tracking_number,
        subtitle: ev.status,
        time: this.timeAgo(ev.created_at),
        icon: 'package',
      });
    }
    for (const t of (ws?.recent_tickets ?? []).slice(0, 2)) {
      items.push({
        title: t.ticket_number,
        subtitle: this.i18n.t('employee.assistant.activityTicketUpdated'),
        time: this.timeAgo(t.created_at),
        icon: 'ticket',
      });
    }
    if (items.length < 4) {
      items.push(
        { title: 'POD_456.pdf', subtitle: this.i18n.t('employee.assistant.activityDocUploaded'), time: '1h', icon: 'file' },
        { title: 'ARC Logistics', subtitle: this.i18n.t('employee.assistant.activityNewShipment'), time: '2h', icon: 'users' },
      );
    }
    return items.slice(0, 4);
  }

  refreshSessions(): void {
    this.sessions = this.assistantState.listSessions();
    if (this.activeSession) {
      this.activeSession = this.assistantState.getSession(this.activeSession.id);
    }
  }

  newChat(): void {
    this.activeSession = this.assistantState.createSession(this.i18n.t('employee.assistant.newChatTitle'));
    this.pendingAttachments = [];
    this.draft = '';
    this.refreshSessions();
  }

  selectSession(session: EmployeeAssistantSession): void {
    this.activeSession = this.assistantState.getSession(session.id);
    this.pendingAttachments = [];
    this.draft = '';
    this.scrollThread();
  }

  deleteSession(session: EmployeeAssistantSession, event: Event): void {
    event.stopPropagation();
    this.assistantState.deleteSession(session.id);
    if (this.activeSession?.id === session.id) {
      this.activeSession = null;
      this.selectFirstOrNew();
    } else {
      this.refreshSessions();
    }
  }

  startRename(session: EmployeeAssistantSession, event: Event): void {
    event.stopPropagation();
    this.renamingId = session.id;
    this.renameDraft = session.title;
  }

  saveRename(session: EmployeeAssistantSession): void {
    const title = this.renameDraft.trim();
    if (title) {
      this.assistantState.renameSession(session.id, title);
      this.refreshSessions();
      if (this.activeSession?.id === session.id) {
        this.activeSession = this.assistantState.getSession(session.id);
      }
    }
    this.renamingId = null;
    this.renameDraft = '';
  }

  cancelRename(): void {
    this.renamingId = null;
    this.renameDraft = '';
  }

  runQuickAction(promptKey: string): void {
    this.draft = this.i18n.t(promptKey);
    this.send();
  }

  triggerAttachment(): void {
    this.fileInput?.nativeElement.click();
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (!files?.length) return;

    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = () => {
        this.pendingAttachments.push({
          name: file.name,
          mimeType: file.type || 'application/octet-stream',
          dataUrl: String(reader.result ?? ''),
        });
      };
      reader.readAsDataURL(file);
    });
    input.value = '';
  }

  removeAttachment(index: number): void {
    this.pendingAttachments.splice(index, 1);
  }

  onComposerEnter(event: Event): void {
    const ke = event as KeyboardEvent;
    if (ke.shiftKey) return;
    event.preventDefault();
    this.send();
  }

  send(): void {
    const text = this.draft.trim();
    if ((!text && !this.pendingAttachments.length) || this.loading) return;

    this.ensureActiveSession();
    const session = this.activeSession!;
    const attachmentNote = this.pendingAttachments.length
      ? `\n\n[${this.i18n.t('employee.assistant.attachmentLabel')}: ${this.pendingAttachments.map((a) => a.name).join(', ')}]`
      : '';
    const userText = (text || this.i18n.t('employee.assistant.attachmentOnly')) + attachmentNote;

    session.messages.push({
      role: 'user',
      text: userText,
      attachments: [...this.pendingAttachments],
      createdAt: new Date().toISOString(),
    });

    if (session.messages.length === 1) {
      session.title = text.slice(0, 48) || this.i18n.t('employee.assistant.newChatTitle');
    }

    this.assistantState.saveSession(session);
    this.draft = '';
    this.pendingAttachments = [];
    this.loading = true;
    this.scrollThread();

    this.employee.askAi(userText).subscribe({
      next: (res) => {
        session.messages.push({
          role: 'assistant',
          text: res.reply,
          createdAt: new Date().toISOString(),
          tracking: res.tracking,
          clients: res.clients,
          tickets: res.tickets,
          documents: res.documents,
        });
        this.assistantState.saveSession(session);
        this.activeSession = this.assistantState.getSession(session.id);
        this.refreshSessions();
        this.loading = false;
        this.scrollThread();
      },
      error: () => {
        session.messages.push({
          role: 'assistant',
          text: this.i18n.t('employee.copilot.error'),
          createdAt: new Date().toISOString(),
        });
        this.assistantState.saveSession(session);
        this.activeSession = this.assistantState.getSession(session.id);
        this.loading = false;
        this.scrollThread();
      },
    });
  }

  formatMarkdown(text: string): SafeHtml {
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');
    html = html.replace(/\n/g, '<br/>');
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  trackingView(tracking: EmployeeAiTrackingResult): TrackingCardView {
    const isDemo = tracking.tracking_number === '123456789';
    return {
      tracking,
      origin: isDemo ? 'New York, USA' : tracking.current_location || '—',
      destination: isDemo ? 'Paris, France' : '—',
      lastUpdate: isDemo ? 'May 24, 2025 - 08:45 AM' : tracking.events?.[tracking.events.length - 1]?.at || '—',
    };
  }

  trackingSteps(status: string): TimelineStep[] {
    const s = (status || '').toLowerCase();
    let activeIndex = 1;
    if (s.includes('deliver') && !s.includes('out')) activeIndex = 3;
    else if (s.includes('out')) activeIndex = 2;
    else if (s.includes('transit') || s.includes('route')) activeIndex = 1;
    else if (s.includes('pick')) activeIndex = 0;

    const keys = [
      'employee.assistant.timelinePickedUp',
      'employee.assistant.timelineInTransit',
      'employee.assistant.timelineOutForDelivery',
      'employee.assistant.timelineDelivered',
    ];

    return keys.map((labelKey, i) => ({
      labelKey,
      done: i < activeIndex,
      active: i === activeIndex,
    }));
  }

  statusBadgeClass(status: string): string {
    const s = (status || '').toLowerCase();
    if (s.includes('deliver')) return 'emp-ai-ws__badge--success';
    if (s.includes('exception') || s.includes('delay')) return 'emp-ai-ws__badge--danger';
    if (s.includes('transit')) return 'emp-ai-ws__badge--transit';
    return 'emp-ai-ws__badge--default';
  }

  sessionTimeAgo(iso: string): string {
    return this.timeAgo(iso);
  }

  toggleHistory(): void {
    this.historyOpen = !this.historyOpen;
  }

  private selectFirstOrNew(): void {
    const first = this.sessions[0];
    if (first) {
      this.selectSession(first);
    } else {
      this.newChat();
    }
  }

  private ensureActiveSession(): void {
    if (!this.activeSession) {
      this.activeSession = this.assistantState.createSession(this.i18n.t('employee.assistant.newChatTitle'));
      this.refreshSessions();
    }
  }

  private scrollThread(): void {
    setTimeout(() => {
      const el = this.threadEl?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }

  private timeAgo(iso: string): string {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return this.i18n.t('employee.ops.justNow');
    if (mins < 60) return `${mins} min`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days === 1) return this.i18n.t('employee.assistant.yesterday');
    return `${days}d`;
  }

  private initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'EM';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  private seedDemoIfEmpty(): void {
    if (this.assistantState.listSessions().length) return;

    const now = Date.now();
    const demoTracking: EmployeeAiTrackingResult = {
      tracking_number: '123456789',
      status: 'In Transit',
      current_location: 'Paris Hub, France',
      estimated_delivery: 'May 26, 2025 before 6:00 PM',
      is_exception: false,
      client_name: 'Mohamed El Amrani',
      events: [
        { label: 'Picked Up', at: 'May 22, 2025' },
        { label: 'In Transit', at: 'May 24, 2025' },
      ],
    };

    const main = this.assistantState.createSession('Tracking 123456789 status');
    main.updatedAt = new Date(now - 2 * 60_000).toISOString();
    main.messages = [
      {
        role: 'user',
        text: this.i18n.t('employee.assistant.promptTracking'),
        createdAt: new Date(now - 2 * 60_000).toISOString(),
      },
      {
        role: 'assistant',
        text: this.i18n.t('employee.assistant.trackingReplyIntro'),
        createdAt: new Date(now - 2 * 60_000 + 5000).toISOString(),
        tracking: demoTracking,
      },
    ];
    this.assistantState.saveSession(main);

    const extras = [
      { title: 'Open support tickets', ago: 60 * 60_000 },
      { title: 'Pending documents', ago: 3 * 60 * 60_000 },
      { title: 'Client Mohamed details', ago: 24 * 60 * 60_000 },
      { title: 'Delivery exceptions', ago: 26 * 60 * 60_000 },
    ];

    extras.forEach(({ title, ago }) => {
      const s = this.assistantState.createSession(title);
      s.updatedAt = new Date(now - ago).toISOString();
      this.assistantState.saveSession(s);
    });
  }
}
