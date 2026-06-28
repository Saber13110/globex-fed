import { CommonModule } from '@angular/common';
import { Component, ElementRef, HostListener, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription, interval } from 'rxjs';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { EmployeeHelpdeskStateService } from '../../../../core/services/employee-helpdesk-state.service';
import {
  EmployeeClientDetail,
  EmployeeHelpdeskEmployeeOption,
  EmployeeHelpdeskMessage,
  EmployeeHelpdeskStats,
  EmployeeHelpdeskTicketDetail,
  EmployeeHelpdeskTicketSummary,
  EmployeePortalService,
} from '../../../../core/services/employee-portal.service';

interface TicketTimelineEvent {
  labelKey: string;
  detail?: string;
  at: string | null;
  isNow?: boolean;
}
import { SupportService } from '../../../../core/services/support.service';

type InboxTab = 'open' | 'pending' | 'resolved' | 'closed';

@Component({
  selector: 'app-employee-support-page',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe],
  templateUrl: './employee-support-page.component.html',
  styleUrls: ['./employee-support-page.component.scss'],
})
export class EmployeeSupportPageComponent implements OnInit, OnDestroy {
  @ViewChild('threadEl') threadEl?: ElementRef<HTMLDivElement>;

  tickets: EmployeeHelpdeskTicketSummary[] = [];
  selected: EmployeeHelpdeskTicketDetail | null = null;
  selectedId: number | null = null;
  stats: EmployeeHelpdeskStats | null = null;
  employees: EmployeeHelpdeskEmployeeOption[] = [];

  inboxTab: InboxTab = 'open';
  q = '';
  priority = '';
  category = '';
  assigned = '';

  reply = '';
  internalNote = '';
  sending = false;
  noteSending = false;
  assignOpen = false;
  assignEmployeeId: number | null = null;
  showInternalNote = false;
  loadingList = false;
  loadingDetail = false;
  clientSummary: EmployeeClientDetail | null = null;
  actionsOpen = false;

  private readonly readIds = new Set<number>();
  private pollSub?: Subscription;
  private routeSub?: Subscription;

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly support: SupportService,
    private readonly helpdeskState: EmployeeHelpdeskStateService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.loadEmployees();
    this.routeSub = this.route.paramMap.subscribe((params) => {
      const raw = params.get('ticketId');
      const id = raw ? Number(raw) : 0;
      if (id > 0) {
        this.selectTicket(id, false);
      } else {
        this.selectedId = null;
        this.selected = null;
      }
    });
    this.loadInbox();
    this.loadStats();
    this.pollSub = interval(12_000).subscribe(() => {
      this.loadInbox(true);
      this.loadStats();
      if (this.selectedId) {
        this.loadDetail(this.selectedId, true);
      }
    });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
    this.routeSub?.unsubscribe();
  }

  setTab(tab: InboxTab): void {
    this.inboxTab = tab;
    this.loadInbox();
  }

  applyFilters(): void {
    this.loadInbox();
  }

  loadInbox(silent = false): void {
    if (!silent) this.loadingList = true;
    const params: Record<string, string> = { status: this.inboxTab };
    if (this.priority) params['priority'] = this.priority;
    if (this.category) params['category'] = this.category;
    if (this.assigned) params['assigned'] = this.assigned;
    if (this.q.trim()) params['q'] = this.q.trim();
    this.employee.listTickets(params).subscribe({
      next: (res) => {
        this.tickets = res.items.map((t) => ({
          ...t,
          unread: t.unread && !this.readIds.has(t.id),
        }));
        this.loadingList = false;
      },
      error: () => (this.loadingList = false),
    });
  }

  loadStats(): void {
    this.employee.getHelpdeskStats().subscribe({
      next: (s) => {
        this.stats = s;
        this.helpdeskState.setUnread(s.unread);
      },
    });
  }

  loadEmployees(): void {
    this.employee.listHelpdeskEmployees().subscribe({
      next: (rows) => (this.employees = rows),
    });
  }

  @HostListener('document:click')
  closeActionsMenu(): void {
    this.actionsOpen = false;
  }

  toggleActionsMenu(event: Event): void {
    event.stopPropagation();
    this.actionsOpen = !this.actionsOpen;
  }

  runTicketAction(action: string, event?: Event): void {
    event?.stopPropagation();
    this.actionsOpen = false;
    switch (action) {
      case 'reply':
        this.showInternalNote = false;
        break;
      case 'resolve':
        this.setStatus('resolved');
        break;
      case 'pending':
        this.setStatus('pending');
        break;
      case 'escalate':
        this.setStatus('escalated');
        break;
      case 'assign':
        this.openAssign();
        break;
      case 'internal':
        this.showInternalNote = true;
        break;
      case 'profile':
        this.openClientProfile();
        break;
      case 'tracking':
        this.openTracking();
        break;
      case 'download':
        this.downloadAttachments();
        break;
    }
  }

  selectTicket(id: number, updateUrl = true): void {
    this.selectedId = id;
    this.actionsOpen = false;
    this.readIds.add(id);
    this.tickets = this.tickets.map((t) => (t.id === id ? { ...t, unread: false } : t));
    if (updateUrl) {
      void this.router.navigate(['/employee/support', id], { replaceUrl: true });
    }
    this.loadDetail(id);
  }

  loadDetail(id: number, silent = false): void {
    if (!silent) this.loadingDetail = true;
    this.employee.getTicket(id).subscribe({
      next: (t) => {
        const prevUnread = this.selected?.messages?.length ?? 0;
        this.selected = t;
        this.loadingDetail = false;
        this.loadClientSummary(t.client_id);
        if (silent && t.messages.length > prevUnread && t.messages.at(-1)?.author_role === 'user') {
          this.tickets = this.tickets.map((tk) =>
            tk.id === id ? { ...tk, unread: true, last_activity: t.messages.at(-1)?.body?.slice(0, 160) || tk.last_activity } : tk,
          );
          this.readIds.delete(id);
        }
        setTimeout(() => this.scrollThread(), 50);
      },
      error: () => (this.loadingDetail = false),
    });
  }

  sendReply(): void {
    if (!this.selected || !this.reply.trim() || this.sending) return;
    this.sending = true;
    this.employee.replyTicket(this.selected.id, this.reply.trim()).subscribe({
      next: (msg) => {
        this.selected!.messages = [...this.selected!.messages, { ...msg, is_internal: false }];
        this.selected!.status = this.selected!.status === 'open' ? 'pending' : this.selected!.status;
        this.reply = '';
        this.sending = false;
        this.loadInbox(true);
        this.loadStats();
        this.scrollThread();
      },
      error: () => (this.sending = false),
    });
  }

  sendInternalNote(): void {
    if (!this.selected || !this.internalNote.trim() || this.noteSending) return;
    this.noteSending = true;
    this.employee.addInternalNote(this.selected.id, this.internalNote.trim()).subscribe({
      next: (msg) => {
        this.selected!.messages = [...this.selected!.messages, msg];
        this.internalNote = '';
        this.noteSending = false;
        this.showInternalNote = false;
        this.scrollThread();
      },
      error: () => (this.noteSending = false),
    });
  }

  setStatus(status: string): void {
    if (!this.selected) return;
    this.employee.updateTicketStatus(this.selected.id, status).subscribe({
      next: (t) => {
        this.selected!.status = t.status;
        this.loadInbox(true);
        this.loadStats();
      },
    });
  }

  openAssign(): void {
    this.assignEmployeeId = this.selected?.assigned_employee_id ?? null;
    this.assignOpen = true;
  }

  confirmAssign(): void {
    if (!this.selected) return;
    this.employee.assignTicket(this.selected.id, this.assignEmployeeId).subscribe({
      next: (t) => {
        this.selected = t;
        this.assignOpen = false;
        this.loadInbox(true);
      },
    });
  }

  onReplyFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !this.selected) return;
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.employee.replyTicket(this.selected!.id, this.reply.trim() || 'Pièce jointe', res.url).subscribe({
          next: () => this.loadDetail(this.selected!.id),
        });
      },
    });
    input.value = '';
  }

  onNoteFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !this.selected) return;
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.employee.addInternalNote(this.selected!.id, this.internalNote.trim() || 'Pièce jointe', res.url).subscribe({
          next: () => this.loadDetail(this.selected!.id),
        });
      },
    });
    input.value = '';
  }

  openAttachment(url: string): void {
    this.support.openAttachment(url).subscribe({
      error: () => window.alert('Impossible d\'ouvrir la pièce jointe.'),
    });
  }

  openClientProfile(): void {
    if (!this.selected) return;
    void this.router.navigate(['/employee/client', this.selected.client_id]);
  }

  openTracking(): void {
    if (!this.selected?.tracking_number) return;
    void this.router.navigate(['/employee/tracking', this.selected.tracking_number]);
  }

  downloadAttachments(): void {
    if (!this.selected) return;
    const urls: string[] = [];
    if (this.selected.attachment_url) urls.push(this.selected.attachment_url);
    for (const m of this.selected.messages) {
      if (m.attachment_url) urls.push(m.attachment_url);
    }
    for (const url of urls) {
      this.support.openAttachment(url).subscribe({
        error: () => window.alert('Impossible de télécharger une pièce jointe.'),
      });
    }
  }

  tabCount(tab: InboxTab): number {
    if (!this.stats) return 0;
    if (tab === 'open') return this.stats.open;
    if (tab === 'pending') return this.stats.pending;
    if (tab === 'resolved') return this.stats.resolved;
    return this.stats.closed;
  }

  bubbleClass(role: string, internal: boolean): string {
    if (internal) return 'helpdesk-bubble helpdesk-bubble--internal';
    if (role === 'user') return 'helpdesk-bubble helpdesk-bubble--customer';
    if (role === 'admin') return 'helpdesk-bubble helpdesk-bubble--admin';
    return 'helpdesk-bubble helpdesk-bubble--employee';
  }

  msgWrapperClass(role: string, internal: boolean): string {
    if (internal) return 'helpdesk-msg helpdesk-msg--internal';
    if (role === 'user') return 'helpdesk-msg helpdesk-msg--customer';
    return 'helpdesk-msg helpdesk-msg--staff';
  }

  msgRoleKey(msg: EmployeeHelpdeskMessage): string {
    if (msg.is_internal) return 'employee.helpdesk.roleInternal';
    if (msg.author_role === 'user') return 'employee.helpdesk.roleClient';
    if (msg.author_role === 'admin') return 'employee.helpdesk.roleAdmin';
    return 'employee.helpdesk.roleEmployee';
  }

  customerInitials(): string {
    if (this.clientSummary?.avatar_initials) return this.clientSummary.avatar_initials;
    const name = this.selected?.customer_name?.trim() || '';
    if (!name) return '?';
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  }

  priorityKpiClass(priority: string): string {
    const p = (priority || '').toLowerCase();
    if (p === 'high') return 'helpdesk-kpi--high';
    if (p === 'medium') return 'helpdesk-kpi--medium';
    if (p === 'low') return 'helpdesk-kpi--low';
    return '';
  }

  ticketTimeline(): TicketTimelineEvent[] {
    const t = this.selected;
    if (!t) return [];

    const events: TicketTimelineEvent[] = [
      { labelKey: 'employee.helpdesk.event.created', at: t.created_at },
    ];

    if (t.assigned_employee) {
      events.push({
        labelKey: 'employee.helpdesk.event.assigned',
        detail: t.assigned_employee,
        at: t.updated_at && t.updated_at !== t.created_at ? t.updated_at : t.created_at,
      });
    }

    const publicMessages = t.messages.filter((m) => !m.is_internal);
    for (const m of publicMessages) {
      if (m.author_role === 'user') {
        events.push({ labelKey: 'employee.helpdesk.event.customerReplied', at: m.created_at });
      } else {
        events.push({
          labelKey: 'employee.helpdesk.event.employeeReplied',
          detail: m.author_name || undefined,
          at: m.created_at,
        });
      }
    }

    const lastPublic = publicMessages.at(-1);
    let nowKey = 'employee.helpdesk.event.waitingForEmployee';
    if (t.status === 'resolved' || t.status === 'closed') {
      nowKey = 'employee.helpdesk.event.resolved';
    } else if (t.status === 'escalated') {
      nowKey = 'employee.helpdesk.event.escalated';
    } else if (t.status === 'pending' && lastPublic?.author_role !== 'user') {
      nowKey = 'employee.helpdesk.event.waitingForCustomer';
    }
    events.push({ labelKey: nowKey, at: null, isNow: true });

    return events;
  }

  formatTimelineDate(iso: string): string {
    const d = new Date(iso);
    const day = d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return `${day} ${time}`;
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
  }

  formatTime(iso: string): string {
    return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  relativeActivity(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    return `${Math.floor(hrs / 24)}d`;
  }

  private loadClientSummary(clientId: number): void {
    this.clientSummary = null;
    if (!clientId) return;
    this.employee.getClient(clientId).subscribe({
      next: (c) => (this.clientSummary = c),
      error: () => {},
    });
  }

  private scrollThread(): void {
    const el = this.threadEl?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }
}
