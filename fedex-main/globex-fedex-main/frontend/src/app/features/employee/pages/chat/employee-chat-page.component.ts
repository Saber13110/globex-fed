import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AuthService } from '../../../../core/services/auth.service';
import {
  EmployeeAiAction,
  EmployeeAiClientResult,
  EmployeeAiDocumentResult,
  EmployeeAiResponse,
  EmployeeAiTicketResult,
  EmployeeAiTrackingResult,
  EmployeeChatContextPanel,
  EmployeePortalService,
} from '../../../../core/services/employee-portal.service';

interface CopilotMessage {
  role: 'user' | 'assistant';
  text: string;
  intent?: string;
  clients?: EmployeeAiClientResult[];
  tracking?: EmployeeAiTrackingResult | null;
  tickets?: EmployeeAiTicketResult[];
  documents?: EmployeeAiDocumentResult[];
  admin_draft?: string | null;
  actions?: EmployeeAiAction[];
  html?: SafeHtml;
}

interface QuickAction {
  icon: string;
  titleKey: string;
  descKey: string;
  promptKey?: string;
  route?: string;
}

interface SuggestedPrompt {
  key: string;
}

@Component({
  selector: 'app-employee-chat-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-chat-page.component.html',
  styleUrl: './employee-chat-page.component.scss',
})
export class EmployeeChatPageComponent implements OnInit {
  @ViewChild('threadEl') threadEl?: ElementRef<HTMLElement>;

  messages: CopilotMessage[] = [];
  draft = '';
  loading = false;
  accountName = '';
  employeeInitials = 'EM';
  context: EmployeeChatContextPanel | null = null;
  contextLoading = true;

  readonly quickActions: QuickAction[] = [
    { icon: 'users', titleKey: 'employee.copilot.actionClient', descKey: 'employee.copilot.actionClientDesc', promptKey: 'employee.copilot.promptClient' },
    { icon: 'package', titleKey: 'employee.copilot.actionTracking', descKey: 'employee.copilot.actionTrackingDesc', promptKey: 'employee.copilot.promptTracking' },
    { icon: 'ticket', titleKey: 'employee.copilot.actionTickets', descKey: 'employee.copilot.actionTicketsDesc', promptKey: 'employee.copilot.promptTickets' },
    { icon: 'file', titleKey: 'employee.copilot.actionDocs', descKey: 'employee.copilot.actionDocsDesc', promptKey: 'employee.copilot.promptDocs' },
    { icon: 'alert', titleKey: 'employee.copilot.actionExceptions', descKey: 'employee.copilot.actionExceptionsDesc', promptKey: 'employee.copilot.promptExceptions' },
    { icon: 'message', titleKey: 'employee.copilot.actionAdmin', descKey: 'employee.copilot.actionAdminDesc', route: '/employee/admin-chat' },
  ];

  readonly suggestedPrompts: SuggestedPrompt[] = [
    { key: 'employee.copilot.promptClient' },
    { key: 'employee.copilot.promptTickets' },
    { key: 'employee.copilot.promptTracking' },
    { key: 'employee.copilot.promptExceptions' },
    { key: 'employee.copilot.promptDocs' },
    { key: 'employee.copilot.promptClientsWeek' },
    { key: 'employee.copilot.promptNotifs' },
    { key: 'employee.copilot.promptSummary' },
  ];

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
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
    this.loadContext();
    const q = this.route.snapshot.queryParamMap.get('q');
    if (q) {
      this.draft = q;
      this.send();
    }
  }

  loadContext(): void {
    this.contextLoading = true;
    this.employee.getChatContext().subscribe({
      next: (ctx) => {
        this.context = ctx;
        this.contextLoading = false;
      },
      error: () => (this.contextLoading = false),
    });
  }

  usePrompt(key: string): void {
    this.draft = this.i18n.t(key);
    this.focusInput();
  }

  runQuickAction(action: QuickAction): void {
    if (action.route) {
      void this.router.navigateByUrl(action.route);
      return;
    }
    if (action.promptKey) {
      this.draft = this.i18n.t(action.promptKey);
      this.send();
    }
  }

  send(): void {
    const text = this.draft.trim();
    if (!text || this.loading) return;
    this.messages.push({ role: 'user', text });
    this.draft = '';
    this.loading = true;
    this.scrollThread();

    this.employee.askAi(text).subscribe({
      next: (res) => this.pushAssistant(res),
      error: () => {
        this.messages.push({
          role: 'assistant',
          text: this.i18n.t('employee.copilot.error'),
          html: this.formatMarkdown(this.i18n.t('employee.copilot.error')),
        });
        this.loading = false;
        this.scrollThread();
      },
    });
  }

  sendAdminDraft(draft: string): void {
    void this.router.navigate(['/employee/admin-chat'], { queryParams: { draft } });
  }

  priorityClass(p: string): string {
    const v = (p || 'medium').toLowerCase();
    if (v === 'high') return 'copilot-priority--high';
    if (v === 'low') return 'copilot-priority--low';
    return 'copilot-priority--medium';
  }

  statusClass(s: string): string {
    return `copilot-status--${(s || 'open').toLowerCase()}`;
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

  private pushAssistant(res: EmployeeAiResponse): void {
    this.messages.push({
      role: 'assistant',
      text: res.reply,
      intent: res.intent,
      clients: res.clients,
      tracking: res.tracking,
      tickets: res.tickets,
      documents: res.documents,
      admin_draft: res.admin_draft,
      actions: res.actions,
      html: this.formatMarkdown(res.reply),
    });
    this.loading = false;
    this.loadContext();
    this.scrollThread();
  }

  private scrollThread(): void {
    setTimeout(() => {
      const el = this.threadEl?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }

  private focusInput(): void {
    /* input focused via user click on prompt */
  }

  private initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'EM';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
}
