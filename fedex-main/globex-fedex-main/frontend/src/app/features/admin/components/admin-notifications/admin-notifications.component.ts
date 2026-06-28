import { animate, style, transition, trigger } from '@angular/animations';
import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnDestroy, OnInit, Output, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  NotificationItem,
  NotificationOverview,
  NotificationPreferences,
  NotificationTab,
  NotificationsService,
} from '../../../../core/services/notifications.service';
import { AdminService } from '../../../../core/services/admin.service';
import { AdminSupportDrawerComponent } from '../admin-support-drawer/admin-support-drawer.component';

@Component({
  selector: 'app-admin-notifications',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule, AdminSupportDrawerComponent],
  templateUrl: './admin-notifications.component.html',
  styleUrl: './admin-notifications.component.scss',
  animations: [
    trigger('fadeIn', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(8px)' }),
        animate('240ms ease-out', style({ opacity: 1, transform: 'translateY(0)' })),
      ]),
    ]),
    trigger('slideIn', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateX(-8px)' }),
        animate('200ms ease-out', style({ opacity: 1, transform: 'translateX(0)' })),
      ]),
    ]),
  ],
})
export class AdminNotificationsComponent implements OnInit, OnDestroy {
  @Output() navigate = new EventEmitter<string>();
  @Output() unreadChange = new EventEmitter<number>();

  readonly tabs: { id: NotificationTab | 'support'; label: string }[] = [
    { id: 'all', label: 'Tous' },
    { id: 'support', label: 'Support' },
    { id: 'colis', label: 'Colis' },
    { id: 'ia', label: 'IA' },
    { id: 'users', label: 'Utilisateurs' },
    { id: 'system', label: 'Système' },
    { id: 'incidents', label: 'Incidents' },
  ];

  readonly loading = signal(true);
  readonly listLoading = signal(false);
  readonly error = signal<string | null>(null);
  readonly overview = signal<NotificationOverview | null>(null);
  readonly items = signal<NotificationItem[]>([]);
  readonly total = signal(0);
  readonly unread = signal(0);

  readonly activeTab = signal<NotificationTab | 'support'>('all');
  readonly search = signal('');
  readonly sort = signal('newest');
  readonly page = signal(1);
  readonly pageSize = signal(6);
  readonly showFilters = signal(false);
  readonly filterStatus = signal('all');
  readonly filterPriority = signal('all');
  readonly filterChannel = signal('all');
  readonly openMenuId = signal<number | null>(null);
  readonly prefs = signal<NotificationPreferences>({
    web_enabled: true,
    email_enabled: true,
    sms_enabled: false,
    ai_reports: true,
    incidents: true,
  });
  readonly showSettings = signal(false);
  readonly supportDrawerOpen = signal(false);
  readonly supportTicketId = signal<number | null>(null);

  readonly kpis = computed(() => this.overview()?.stats.kpis ?? []);
  readonly timeline = computed(() => this.overview()?.timeline ?? []);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize())));
  readonly rangeLabel = computed(() => {
    const t = this.total();
    if (!t) return 'Showing 0 notifications';
    const start = (this.page() - 1) * this.pageSize() + 1;
    const end = Math.min(this.page() * this.pageSize(), t);
    return `Showing ${start} to ${end} of ${t} notifications`;
  });

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly api: NotificationsService,
    private readonly admin: AdminService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.reload();
    this.api.getPreferences().subscribe({ next: (p) => this.prefs.set(p) });
    this.connectStream();
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getOverview().subscribe({
      next: (o) => {
        this.overview.set(o);
        this.unread.set(o.stats.unread_count);
        this.unreadChange.emit(o.stats.unread_count);
        this.loading.set(false);
        this.loadList();
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Impossible de charger le Notification Center.');
      },
    });
  }

  loadList(): void {
    this.listLoading.set(true);
    this.api
      .list({
        tab: this.activeTab() === 'support' ? 'incidents' : this.activeTab(),
        search: this.search(),
        sort: this.sort(),
        status: this.filterStatus(),
        priority: this.filterPriority(),
        channel: this.filterChannel(),
        page: this.page(),
        page_size: this.pageSize(),
      })
      .subscribe({
        next: (r) => {
          this.items.set(r.items);
          this.total.set(r.total);
          this.unread.set(r.unread_count);
          this.unreadChange.emit(r.unread_count);
          this.listLoading.set(false);
        },
        error: () => {
          this.listLoading.set(false);
          this.toast('Erreur de chargement des notifications.', 'error');
        },
      });
  }

  setTab(tab: NotificationTab | 'support'): void {
    this.activeTab.set(tab);
    this.page.set(1);
    this.loadList();
  }

  applySearch(): void {
    this.page.set(1);
    this.loadList();
  }

  markAllRead(): void {
    this.api.markAllRead().subscribe({
      next: () => {
        this.toast('Toutes les notifications marquées comme lues.', 'success');
        this.reload();
      },
      error: () => this.toast('Échec.', 'error'),
    });
  }

  exportHistory(fmt: 'csv' | 'xlsx'): void {
    this.api.exportHistory(fmt);
    this.toast(`Export ${fmt.toUpperCase()} lancé.`, 'success');
  }

  openSettingsPanel(): void {
    this.showSettings.set(true);
    this.navigate.emit('settings');
    this.toast('Ouvrez l’onglet Notifications dans Settings.', 'success');
  }

  togglePref(key: keyof NotificationPreferences): void {
    const current = { ...this.prefs() };
    current[key] = !current[key];
    this.prefs.set(current);
    this.api.savePreferences({ [key]: current[key] }).subscribe({
      next: (p) => {
        this.prefs.set(p);
        this.toast('Préférences enregistrées.', 'success');
      },
      error: () => this.toast('Échec de sauvegarde.', 'error'),
    });
  }

  runAction(item: NotificationItem): void {
    this.markRead(item, true);
    const type = item.action_type;
    if (type === 'support_ticket') {
      const id = Number(item.action_ref);
      if (Number.isFinite(id) && id > 0) {
        this.supportTicketId.set(id);
        this.supportDrawerOpen.set(true);
      }
      return;
    }
    if (type === 'employee_chat') {
      this.navigate.emit('conversations');
      return;
    }
    if (type === 'tracking') this.navigate.emit('tracking');
    else if (type === 'security_suspend_user') this.suspendFromNotification(item);
    else if (type === 'user') this.navigate.emit('users');
    else if (type === 'report') this.navigate.emit('reports');
    else if (type === 'ai') this.navigate.emit('ai-assistant');
    else if (type === 'incident' || type === 'security_incident') this.navigate.emit('incidents');
  }

  suspendFromNotification(item: NotificationItem): void {
    const uid = Number(item.action_ref);
    if (!Number.isFinite(uid) || uid <= 0) return;
    const ok = confirm(
      `${item.title}\n\n${item.message}\n\nSuspendre ce compte maintenant ?`,
    );
    if (!ok) return;
    this.admin.suspendUser(uid, item.message).subscribe({
      next: () => {
        this.toast('Compte suspendu.', 'success');
        this.reload();
      },
      error: (err) => {
        this.toast(typeof err.error?.detail === 'string' ? err.error.detail : 'Suspension impossible.', 'error');
      },
    });
  }

  canSuspendNotification(item: NotificationItem): boolean {
    return item.action_type === 'security_suspend_user' && Number(item.action_ref) > 0;
  }

  openSupportDrawerFromItem(item: NotificationItem, event: Event): void {
    event.stopPropagation();
    this.runAction(item);
  }

  closeSupportDrawer(): void {
    this.supportDrawerOpen.set(false);
    this.supportTicketId.set(null);
  }

  onSupportUpdated(): void {
    this.reload();
  }

  markRead(item: NotificationItem, read: boolean): void {
    this.api.markRead(item.id, read).subscribe({
      next: () => this.reload(),
      error: () => this.toast('Échec.', 'error'),
    });
  }

  archiveItem(item: NotificationItem): void {
    this.api.archive(item.id).subscribe({
      next: () => {
        this.toast('Notification archivée.', 'success');
        this.openMenuId.set(null);
        this.reload();
      },
      error: () => this.toast('Échec.', 'error'),
    });
  }

  deleteItem(item: NotificationItem): void {
    if (!confirm('Supprimer cette notification ?')) return;
    this.api.delete(item.id).subscribe({
      next: () => {
        this.toast('Notification supprimée.', 'success');
        this.openMenuId.set(null);
        this.reload();
      },
      error: () => this.toast('Échec.', 'error'),
    });
  }

  copyTracking(item: NotificationItem): void {
    if (!item.tracking_number) return;
    navigator.clipboard?.writeText(item.tracking_number);
    this.toast('Numéro copié.', 'success');
    this.openMenuId.set(null);
  }

  toggleMenu(id: number, event: Event): void {
    event.stopPropagation();
    this.openMenuId.set(this.openMenuId() === id ? null : id);
  }

  rowIcon(icon: string): string {
    const map: Record<string, string> = {
      truck: 'truck',
      check: 'check',
      brain: 'brain',
      user: 'user',
      alert: 'alert',
      bell: 'bell',
      package: 'package',
      mail: 'mail',
      server: 'server',
      cog: 'cog',
    };
    return map[icon] ?? 'bell';
  }

  sparkPath(values: number[]): string {
    if (!values.length) return '';
    const w = 72;
    const h = 28;
    const max = Math.max(...values, 1);
    const min = Math.min(...values);
    const range = max - min || 1;
    const pts = values.map((v, i) => {
      const x = (i / (values.length - 1 || 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    });
    return `M ${pts.join(' L ')}`;
  }

  kpiIcon(icon: string): string {
    return icon;
  }

  categoryLabel(cat: string): string {
    const map: Record<string, string> = {
      colis: 'Colis',
      ia: 'IA',
      users: 'Utilisateurs',
      system: 'Système',
      incidents: 'Incidents',
    };
    return map[cat] ?? cat;
  }

  categoryClass(cat: string): string {
    return `ntf-cat--${cat}`;
  }

  iconClass(icon: string): string {
    return `ntf-icon--${icon}`;
  }

  pageNumbers(): number[] {
    const tp = this.totalPages();
    const p = this.page();
    if (tp <= 5) return Array.from({ length: tp }, (_, i) => i + 1);
    if (p <= 3) return [1, 2, 3, -1, tp];
    if (p >= tp - 2) return [1, -1, tp - 2, tp - 1, tp];
    return [1, -1, p, -1, tp];
  }

  goPage(n: number): void {
    if (n < 1 || n > this.totalPages() || n === -1) return;
    this.page.set(n);
    this.loadList();
  }

  private connectStream(): void {
    this.pollTimer = setInterval(() => {
      this.api.getUnreadCount().subscribe({
        next: ({ count }) => {
          const prev = this.unread();
          if (count !== prev) {
            this.unread.set(count);
            this.unreadChange.emit(count);
            if (count > prev) {
              this.toast('Nouvelle notification reçue.', 'success');
              this.loadList();
            }
          }
        },
      });
    }, 20_000);
  }

  private toast(msg: string, type: 'success' | 'error'): void {
    this.snack.open(msg, 'Fermer', {
      duration: 4000,
      panelClass: type === 'success' ? 'set-snack--ok' : 'set-snack--err',
      horizontalPosition: 'end',
      verticalPosition: 'top',
    });
  }
}
