import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  LucideActivity,
  LucideArrowLeft,
  LucideBell,
  LucideBuilding2,
  LucideClock,
  LucideDownload,
  LucideFileText,
  LucideGlobe,
  LucideLayoutDashboard,
  LucideMail,
  LucideMapPin,
  LucidePackage,
  LucideTicket,
  LucideTimeline,
  LucideTruck,
  LucideUser,
  provideLucideIcons,
} from '@lucide/angular';
import { Subject, takeUntil } from 'rxjs';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import {
  EmployeeClientActivityEvent,
  EmployeeClientDetail,
  EmployeeDocumentItem,
  EmployeeNotification,
  EmployeePortalService,
  EmployeeTrackingItem,
} from '../../../../core/services/employee-portal.service';
import { SupportTicketRead } from '../../../../core/services/support.service';

type ClientTab = 'overview' | 'shipments' | 'tickets' | 'notifications' | 'activity';

interface ActivityGroup {
  key: string;
  labelKey: string;
  items: EmployeeClientActivityEvent[];
}

@Component({
  selector: 'app-employee-client-detail-page',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    TranslatePipe,
    LucideArrowLeft,
    LucideLayoutDashboard,
    LucidePackage,
    LucideFileText,
    LucideTicket,
    LucideBell,
    LucideTimeline,
    LucideUser,
    LucideActivity,
    LucideMail,
    LucideGlobe,
    LucideBuilding2,
    LucideClock,
    LucideMapPin,
    LucideTruck,
    LucideDownload,
  ],
  providers: [
    provideLucideIcons(
      LucideArrowLeft,
      LucideLayoutDashboard,
      LucidePackage,
      LucideFileText,
      LucideTicket,
      LucideBell,
      LucideTimeline,
      LucideUser,
      LucideActivity,
      LucideMail,
      LucideGlobe,
      LucideBuilding2,
      LucideClock,
      LucideMapPin,
      LucideTruck,
      LucideDownload,
    ),
  ],
  templateUrl: './employee-client-detail-page.component.html',
  styleUrl: './employee-client-detail-page.component.scss',
})
export class EmployeeClientDetailPageComponent implements OnInit, OnDestroy {
  client: EmployeeClientDetail | null = null;
  tab: ClientTab = 'overview';
  trackings: EmployeeTrackingItem[] = [];
  tickets: SupportTicketRead[] = [];
  notifications: EmployeeNotification[] = [];
  activity: EmployeeClientActivityEvent[] = [];
  loading = true;
  tabLoading = false;
  clientId = 0;
  actionError = '';
  actionSuccess = '';

  readonly tabs: ClientTab[] = ['overview', 'shipments', 'tickets', 'notifications', 'activity'];
  readonly kanbanStatuses = ['open', 'pending', 'resolved', 'escalated'] as const;
  readonly iconSize = 17;

  private readonly loadedTabs = new Set<ClientTab>();
  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly employee: EmployeePortalService,
  ) {}

  ngOnInit(): void {
    this.clientId = Number(this.route.snapshot.paramMap.get('id'));
    const tabParam = this.route.snapshot.queryParamMap.get('tab') as ClientTab | null;
    if (tabParam && this.tabs.includes(tabParam)) {
      this.tab = tabParam;
    }
    this.loadClient();
    this.loadTabData(this.tab);

    this.route.queryParamMap.pipe(takeUntil(this.destroy$)).subscribe((params) => {
      const t = params.get('tab') as ClientTab | null;
      if (t && this.tabs.includes(t) && t !== this.tab) {
        this.tab = t;
        this.loadTabData(t);
      }
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadClient(): void {
    this.employee.getClient(this.clientId).subscribe({
      next: (c) => {
        this.client = c;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
    this.employee.getClientShipments(this.clientId).subscribe({ next: (t) => (this.trackings = t) });
    this.employee.getClientTickets(this.clientId).subscribe({ next: (r) => (this.tickets = r.items) });
  }

  loadTabData(tab: ClientTab): void {
    if (this.loadedTabs.has(tab)) return;
    this.loadedTabs.add(tab);

    if (tab === 'overview' || tab === 'activity') {
      this.employee.getClientActivity(this.clientId).subscribe({
        next: (a) => {
          this.activity = a;
          this.tabLoading = false;
        },
        error: () => (this.tabLoading = false),
      });
      if (tab === 'overview') return;
    }

    this.tabLoading = true;

    if (tab === 'shipments') {
      this.employee.getClientShipments(this.clientId).subscribe({
        next: (t) => {
          this.trackings = t;
          this.tabLoading = false;
        },
        error: () => (this.tabLoading = false),
      });
      return;
    }

    if (tab === 'tickets') {
      this.employee.getClientTickets(this.clientId).subscribe({
        next: (r) => {
          this.tickets = r.items;
          this.tabLoading = false;
        },
        error: () => (this.tabLoading = false),
      });
      return;
    }

    if (tab === 'notifications') {
      this.employee.getClientNotifications(this.clientId).subscribe({
        next: (r) => {
          this.notifications = r.items;
          this.tabLoading = false;
        },
        error: () => (this.tabLoading = false),
      });
    }
  }

  setTab(t: ClientTab): void {
    this.tab = t;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab: t },
      queryParamsHandling: 'merge',
    });
    this.loadTabData(t);
  }

  ticketsByStatus(status: string): SupportTicketRead[] {
    return this.tickets.filter((t) => (t.status || '').toLowerCase() === status);
  }

  kanbanLabel(status: string): string {
    const map: Record<string, string> = {
      open: 'employee.clientOps.kanbanOpen',
      pending: 'employee.clientOps.kanbanPending',
      resolved: 'employee.clientOps.kanbanResolved',
      escalated: 'employee.clientOps.kanbanEscalated',
    };
    return map[status] ?? status;
  }

  clientSince(): string {
    if (!this.client) return '—';
    return new Date(this.client.created_at).toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
  }

  lastActivityRelative(): string {
    if (!this.client?.last_activity) return '—';
    const ev = this.activity[0];
    if (ev?.created_at) {
      const diff = Date.now() - new Date(ev.created_at).getTime();
      const hours = Math.floor(diff / 3_600_000);
      if (hours < 1) return '< 1h';
      if (hours < 24) return `${hours}h ago`;
      const days = Math.floor(hours / 24);
      return `${days}d ago`;
    }
    return this.client.last_activity;
  }

  recentShipmentLabel(): string {
    const t = this.trackings[0];
    return t ? `${t.tracking_number} · ${t.status}` : '—';
  }

  recentTicketLabel(): string {
    const t = this.tickets[0];
    return t ? t.subject : '—';
  }

  activityGroups(): ActivityGroup[] {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfYesterday = new Date(startOfToday.getTime() - 86_400_000);
    const startOfWeek = new Date(startOfToday.getTime() - 6 * 86_400_000);
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    const buckets: ActivityGroup[] = [
      { key: 'today', labelKey: 'employee.clientOps.groupToday', items: [] },
      { key: 'yesterday', labelKey: 'employee.clientOps.groupYesterday', items: [] },
      { key: 'week', labelKey: 'employee.clientOps.groupWeek', items: [] },
      { key: 'month', labelKey: 'employee.clientOps.groupMonth', items: [] },
    ];

    for (const ev of this.activity) {
      const d = new Date(ev.created_at);
      if (d >= startOfToday) buckets[0].items.push(ev);
      else if (d >= startOfYesterday) buckets[1].items.push(ev);
      else if (d >= startOfWeek) buckets[2].items.push(ev);
      else if (d >= startOfMonth) buckets[3].items.push(ev);
    }
    return buckets.filter((b) => b.items.length > 0);
  }

  activityColor(kind: string): string {
    if (kind.includes('ticket') || kind === 'support_reply') return 'ticket';
    if (kind.includes('document')) return 'document';
    if (kind.includes('tracking') || kind === 'shipment') return 'shipment';
    return 'notification';
  }

  isException(status: string): boolean {
    const s = (status || '').toLowerCase();
    return s.includes('exception') || s.includes('delay');
  }

  statusClass(status: string): string {
    return `c360-status--${(status || 'open').toLowerCase()}`;
  }

  priorityClass(priority: string | undefined): string {
    const p = (priority || 'medium').toLowerCase();
    if (p === 'high') return 'c360-priority--high';
    if (p === 'low') return 'c360-priority--low';
    return 'c360-priority--medium';
  }

  notifIconKind(kind: string): 'shipment' | 'ticket' | 'document' | 'notification' {
    if (kind.includes('support') || kind.includes('reply') || kind.includes('ticket')) return 'ticket';
    if (kind.includes('tracking')) return 'shipment';
    if (kind.includes('document') || kind.includes('export')) return 'document';
    return 'notification';
  }

  notifCategory(kind: string): string {
    if (kind.includes('support') || kind.includes('reply')) return 'employee.clientOps.notifSupport';
    if (kind.includes('tracking')) return 'employee.clientOps.notifTracking';
    if (kind.includes('document') || kind.includes('export')) return 'employee.clientOps.notifDocument';
    return 'employee.clientOps.notifGeneral';
  }

  downloadDocument(doc: EmployeeDocumentItem): void {
    this.actionError = '';
    this.employee.downloadClientDocument(
      doc,
      () => {
        this.actionError = 'employee.clientOps.actionFailed';
      },
      () => this.flashSuccess('employee.clientOps.downloadStarted'),
    );
  }

  openTicketDetail(id: number): void {
    void this.router.navigate(['/employee/support', id]);
  }

  updateTicketStatus(id: number, status: string): void {
    this.actionError = '';
    this.employee.updateTicketStatus(id, status).subscribe({
      next: (updated) => {
        this.tickets = this.tickets.map((t) => (t.id === id ? updated : t));
        this.flashSuccess('employee.clientOps.ticketUpdated');
      },
      error: () => {
        this.actionError = 'employee.clientOps.actionFailed';
      },
    });
  }

  private flashSuccess(key: string): void {
    this.actionSuccess = key;
    window.setTimeout(() => (this.actionSuccess = ''), 3000);
  }
}
