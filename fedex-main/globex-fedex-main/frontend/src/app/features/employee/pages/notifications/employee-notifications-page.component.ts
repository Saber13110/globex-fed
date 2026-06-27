import { CommonModule } from '@angular/common';
import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import {
  LucideBell,
  LucideCheck,
  LucideChevronLeft,
  LucideChevronRight,
  LucideExternalLink,
  LucideFileText,
  LucideMoreHorizontal,
  LucidePackage,
  LucideRefreshCw,
  LucideSearch,
  LucideShield,
  LucideTicket,
  LucideTrash2,
  LucideX,
  provideLucideIcons,
} from '@lucide/angular';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { I18nService } from '../../../../core/i18n/i18n.service';
import {
  EmployeeNotification,
  EmployeeNotificationStats,
  EmployeePortalService,
} from '../../../../core/services/employee-portal.service';
import { EmployeeNotificationsStateService } from '../../../../core/services/employee-notifications-state.service';
import { EmployeeShellPanelService } from '../../../../core/services/employee-shell-panel.service';

type KpiKey = 'all' | 'unread' | 'support' | 'tracking' | 'documents';
type ToastKind = 'success' | 'error';

@Component({
  selector: 'app-employee-notifications-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    TranslatePipe,
    LucideBell,
    LucideSearch,
    LucideRefreshCw,
    LucideCheck,
    LucideExternalLink,
    LucideMoreHorizontal,
    LucideTrash2,
    LucideTicket,
    LucidePackage,
    LucideFileText,
    LucideShield,
    LucideChevronLeft,
    LucideChevronRight,
    LucideX,
  ],
  providers: [
    provideLucideIcons(
      LucideBell,
      LucideSearch,
      LucideRefreshCw,
      LucideCheck,
      LucideExternalLink,
      LucideMoreHorizontal,
      LucideTrash2,
      LucideTicket,
      LucidePackage,
      LucideFileText,
      LucideShield,
      LucideChevronLeft,
      LucideChevronRight,
      LucideX,
    ),
  ],
  templateUrl: './employee-notifications-page.component.html',
  styleUrl: './employee-notifications-page.component.scss',
})
export class EmployeeNotificationsPageComponent implements OnInit, OnDestroy {
  items: EmployeeNotification[] = [];
  stats: EmployeeNotificationStats = { all: 0, unread: 0, support: 0, tracking: 0, documents: 0, security: 0 };

  search = '';
  typeFilter = '';
  statusFilter = '';
  activeKpi: KpiKey | '' = '';

  page = 1;
  limit = 20;
  total = 0;
  totalPages = 1;
  unreadCount = 0;

  loading = true;
  error = false;
  markingAll = false;
  refreshing = false;
  toast = '';
  toastKind: ToastKind = 'success';
  menuOpenId: number | null = null;

  readonly iconSize = 18;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private toastTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly notifState: EmployeeNotificationsStateService,
    private readonly router: Router,
    private readonly i18n: I18nService,
    private readonly panels: EmployeeShellPanelService,
  ) {}

  ngOnInit(): void {
    this.loadAll();
    this.pollTimer = setInterval(() => this.pollUnread(), 25_000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer !== null) clearInterval(this.pollTimer);
    if (this.toastTimer !== null) clearTimeout(this.toastTimer);
  }

  @HostListener('document:click')
  closeMenus(): void {
    this.menuOpenId = null;
  }

  loadAll(): void {
    this.loading = true;
    this.error = false;
    this.employee.getNotificationStats().subscribe({
      next: (s) => (this.stats = s),
      error: () => {},
    });
    this.fetchList();
  }

  refresh(): void {
    this.refreshing = true;
    this.loadAll();
  }

  applyFilters(): void {
    this.page = 1;
    this.fetchList();
  }

  clearFilters(): void {
    this.search = '';
    this.typeFilter = '';
    this.statusFilter = '';
    this.activeKpi = '';
    this.page = 1;
    this.fetchList();
  }

  selectKpi(key: KpiKey): void {
    this.activeKpi = key;
    this.page = 1;
    if (key === 'unread') this.statusFilter = 'unread';
    else if (key === 'all') this.statusFilter = '';
    else this.statusFilter = '';
    if (key === 'support') this.typeFilter = 'support';
    else if (key === 'tracking') this.typeFilter = 'tracking';
    else if (key === 'documents') this.typeFilter = 'documents';
    else if (key === 'all' || key === 'unread') this.typeFilter = '';
    this.fetchList();
  }

  markAllRead(): void {
    if (this.markingAll || this.unreadCount === 0) return;
    this.markingAll = true;
    this.employee.markAllNotificationsRead().subscribe({
      next: () => {
        this.items = this.items.map((n) => ({ ...n, is_read: true, status: 'read' as const }));
        this.unreadCount = 0;
        this.stats.unread = 0;
        this.notifState.setUnread(0);
        this.markingAll = false;
        this.showToast(this.i18n.t('employee.notifications.allReadDone'), 'success');
        this.employee.getNotificationStats().subscribe({ next: (s) => (this.stats = s) });
      },
      error: () => {
        this.markingAll = false;
        this.showToast(this.i18n.t('employee.notifications.error'), 'error');
      },
    });
  }

  openNotification(n: EmployeeNotification, event?: Event): void {
    event?.stopPropagation();
    const route = this.resolveRoute(n);
    const navigate = () => this.navigateNotification(route);
    if (!n.is_read) {
      this.employee.markNotificationRead(n.id).subscribe({
        next: (updated) => {
          n.is_read = updated.is_read;
          n.status = 'read';
          this.unreadCount = Math.max(0, this.unreadCount - 1);
          this.stats.unread = this.unreadCount;
          this.notifState.setUnread(this.unreadCount);
          navigate();
        },
        error: () => navigate(),
      });
    } else {
      navigate();
    }
  }

  private navigateNotification(route: string): void {
    if (route.includes('panel=settings')) {
      const tab = new URL(route, 'http://local').searchParams.get('tab');
      this.panels.requestSettings(
        tab === 'security' || tab === 'appearance' || tab === 'language' ? tab : 'profile',
      );
      return;
    }
    if (route.includes('panel=help')) {
      this.panels.requestHelp();
      return;
    }
    void this.router.navigateByUrl(route);
  }

  markReadOnly(n: EmployeeNotification, event: Event): void {
    event.stopPropagation();
    if (n.is_read) return;
    this.employee.markNotificationRead(n.id).subscribe({
      next: (updated) => {
        n.is_read = updated.is_read;
        n.status = 'read';
        this.unreadCount = Math.max(0, this.unreadCount - 1);
        this.stats.unread = this.unreadCount;
        this.notifState.setUnread(this.unreadCount);
        this.showToast(this.i18n.t('employee.notifications.markedRead'), 'success');
      },
      error: () => this.showToast(this.i18n.t('employee.notifications.error'), 'error'),
    });
  }

  deleteNotification(n: EmployeeNotification, event: Event): void {
    event.stopPropagation();
    this.menuOpenId = null;
    this.employee.deleteNotification(n.id).subscribe({
      next: () => {
        if (!n.is_read) {
          this.unreadCount = Math.max(0, this.unreadCount - 1);
          this.notifState.setUnread(this.unreadCount);
        }
        this.items = this.items.filter((i) => i.id !== n.id);
        this.total = Math.max(0, this.total - 1);
        this.showToast(this.i18n.t('employee.notifications.deleted'), 'success');
        this.employee.getNotificationStats().subscribe({ next: (s) => (this.stats = s) });
      },
      error: () => this.showToast(this.i18n.t('employee.notifications.error'), 'error'),
    });
  }

  toggleMenu(id: number, event: Event): void {
    event.stopPropagation();
    this.menuOpenId = this.menuOpenId === id ? null : id;
  }

  goPage(delta: number): void {
    const next = this.page + delta;
    if (next < 1 || next > this.totalPages) return;
    this.page = next;
    this.fetchList();
  }

  notifType(n: EmployeeNotification): string {
    return n.type || n.kind || 'system_alert';
  }

  typeLabel(type: string): string {
    const key = `employee.notifications.type.${type}`;
    const t = this.i18n.t(key);
    return t === key ? type : t;
  }

  iconFor(type: string): 'ticket' | 'package' | 'file' | 'shield' | 'bell' | 'message' {
    if (type.includes('support')) return 'ticket';
    if (type.includes('tracking')) return 'package';
    if (type.includes('document')) return 'file';
    if (type.includes('security')) return 'shield';
    if (type.includes('admin')) return 'message';
    return 'bell';
  }

  relativeTime(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return this.i18n.t('employee.notifications.now');
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    const days = Math.floor(hrs / 24);
    if (days < 7) return `${days}d`;
    return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
  }

  kpiValue(key: KpiKey): number {
    return this.stats[key] ?? 0;
  }

  kpiBadge(key: KpiKey): number {
    if (key === 'unread') return this.stats.unread;
    if (key === 'all') return 0;
    return 0;
  }

  private resolveRoute(n: EmployeeNotification): string {
    const type = this.notifType(n);
    if (type === 'support_reply' && n.related_ticket_id) return `/employee/support/${n.related_ticket_id}`;
    if (type === 'tracking_update' && n.related_tracking_number) return `/employee/tracking/${n.related_tracking_number}`;
    if (type === 'document_uploaded') return '/employee/documents';
    if (type === 'admin_message') return '/employee/admin-chat';
    if (type === 'security_alert') return '/employee?panel=settings&tab=security';
    if (n.link?.includes('panel=settings')) return n.link;
    if (n.link?.startsWith('/employee/')) return n.link;
    if (n.link?.startsWith('/employee?')) return n.link;
    return n.link || '/employee/notifications';
  }

  private fetchList(): void {
    const params: Record<string, string> = {
      page: String(this.page),
      limit: String(this.limit),
    };
    if (this.search.trim()) params['search'] = this.search.trim();
    if (this.typeFilter) params['type'] = this.typeFilter;
    if (this.statusFilter) params['status'] = this.statusFilter;

    this.employee.listNotifications(params).subscribe({
      next: (r) => {
        this.items = r.items;
        this.unreadCount = r.unread_count;
        this.total = r.total;
        this.totalPages = r.total_pages;
        this.notifState.setUnread(r.unread_count);
        this.loading = false;
        this.refreshing = false;
        this.error = false;
      },
      error: () => {
        this.loading = false;
        this.refreshing = false;
        this.error = true;
        this.showToast(this.i18n.t('employee.notifications.error'), 'error');
      },
    });
  }

  private pollUnread(): void {
    const prev = this.unreadCount;
    this.employee.getNotificationStats().subscribe({
      next: (s) => {
        if (s.unread > prev) {
          this.showToast(this.i18n.t('employee.notifications.newReceived'), 'success');
          this.loadAll();
        }
        this.stats = s;
        this.unreadCount = s.unread;
        this.notifState.setUnread(s.unread);
      },
    });
  }

  private showToast(message: string, kind: ToastKind): void {
    this.toast = message;
    this.toastKind = kind;
    if (this.toastTimer !== null) clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => {
      this.toast = '';
      this.toastTimer = null;
    }, 3200);
  }
}
