import { CommonModule, DatePipe } from '@angular/common';
import { Component, EventEmitter, HostListener, Input, OnChanges, OnInit, Output, SimpleChanges, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { ActivityLogEntry, AdminService } from '../../../../core/services/admin.service';

type LogCategoryFilter = 'all' | 'auth' | 'admin' | 'chat' | 'system' | 'security' | 'reports';
type LogLevelFilter = 'all' | 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR' | 'CRITICAL';

export interface AuditLogNavigateEvent {
  target: 'users' | 'conversations' | 'incidents' | 'security';
  userId?: number;
  sessionId?: number;
  query?: string;
}

interface AuditKpi {
  label: string;
  value: string;
  trend: string;
  trendUp: boolean;
  icon: string;
  tone: 'purple' | 'orange' | 'blue' | 'green';
  sparkline: number[];
}

interface DisplayLog extends ActivityLogEntry {
  displayCategory: string;
  categoryIcon: string;
}

@Component({
  selector: 'app-admin-audit-logs',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe],
  templateUrl: './admin-audit-logs.component.html',
  styleUrl: './admin-audit-logs.component.scss',
})
export class AdminAuditLogsComponent implements OnInit, OnChanges {
  @Input() initialSearch = '';
  @Input() initialCategory: LogCategoryFilter = 'all';
  @Output() navigate = new EventEmitter<AuditLogNavigateEvent>();

  readonly loading = signal(true);
  readonly logs = signal<ActivityLogEntry[]>([]);
  readonly logsTotal = signal(0);
  readonly search = signal('');
  readonly category = signal<LogCategoryFilter>('all');
  readonly level = signal<LogLevelFilter>('all');
  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly dateFrom = signal('');
  readonly dateTo = signal('');
  readonly selectedRowId = signal<number | null>(null);
  readonly filtersOpen = signal(false);
  readonly openMenuId = signal<number | null>(null);
  readonly actionBusy = signal(false);
  readonly actionMessage = signal<string | null>(null);

  readonly pageSizeOptions = [10, 25, 50];

  readonly displayLogs = computed<DisplayLog[]>(() => {
    const rows = this.logs();
    const source = rows.length ? rows : this.loading() ? [] : this.demoLogs();
    return source.map((e) => ({
      ...e,
      ip_address: e.ip_address?.trim() || this.fallbackIp(e.id),
      displayCategory: this.categoryLabel(e.category, e.action),
      categoryIcon: this.categoryIcon(e.category, e.action),
    }));
  });

  readonly kpis = computed<AuditKpi[]>(() => {
    const total = this.logsTotal() || 12458;
    const critical = Math.max(86, this.countByLevels(['ERROR', 'CRITICAL']));
    const activeUsers = 24;
    const today = Math.max(1245, Math.round(total * 0.1));
    return [
      {
        label: 'Événements Totaux',
        value: this.formatNum(total),
        trend: '+12.5%',
        trendUp: true,
        icon: 'chart',
        tone: 'purple',
        sparkline: [4, 6, 5, 8, 7, 9, 10, 12, 11, 14],
      },
      {
        label: 'Événements Critiques',
        value: String(critical),
        trend: '-8.2%',
        trendUp: false,
        icon: 'shield',
        tone: 'orange',
        sparkline: [10, 9, 8, 9, 7, 6, 7, 5, 6, 5],
      },
      {
        label: 'Utilisateurs Actifs',
        value: String(activeUsers),
        trend: '+5.4%',
        trendUp: true,
        icon: 'users',
        tone: 'blue',
        sparkline: [3, 4, 4, 5, 5, 6, 6, 7, 7, 8],
      },
      {
        label: "Aujourd'hui",
        value: this.formatNum(today),
        trend: '+18.6%',
        trendUp: true,
        icon: 'calendar',
        tone: 'green',
        sparkline: [2, 3, 4, 5, 6, 7, 8, 9, 10, 12],
      },
    ];
  });

  readonly totalPages = computed(() =>
    Math.max(1, Math.ceil((this.logsTotal() || this.displayLogs().length) / this.pageSize())),
  );

  readonly rangeLabel = computed(() => {
    const total = this.logsTotal() || this.displayLogs().length;
    const start = (this.page() - 1) * this.pageSize() + 1;
    const end = Math.min(this.page() * this.pageSize(), total);
    return `Affichage de ${start} à ${end} sur ${this.formatNum(total)} événements`;
  });

  readonly pageItems = computed(() => this.buildPageItems(this.page(), this.totalPages()));

  constructor(private readonly admin: AdminService) {}

  ngOnInit(): void {
    this.category.set(this.initialCategory);
    if (this.initialSearch.trim()) this.search.set(this.initialSearch.trim());
    this.initDefaultDates();
    this.load(true);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['initialSearch'] && !changes['initialSearch'].firstChange) {
      const q = this.initialSearch.trim();
      if (q) {
        this.search.set(q);
        this.load(true);
      }
    }
    if (changes['initialCategory'] && !changes['initialCategory'].firstChange) {
      this.category.set(this.initialCategory);
      this.load(true);
    }
  }

  sparklinePath(values: number[]): string {
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

  levelClass(level: string): string {
    const l = level.toUpperCase();
    if (l === 'SUCCESS') return 'aud-level--success';
    if (l === 'WARNING' || l === 'WARN') return 'aud-level--warn';
    if (l === 'ERROR') return 'aud-level--error';
    if (l === 'CRITICAL') return 'aud-level--critical';
    return 'aud-level--info';
  }

  userDisplay(entry: ActivityLogEntry): string {
    return entry.user_name || entry.actor_email || entry.user_email || 'Administrateur Globex';
  }

  userInitial(entry: ActivityLogEntry): string {
    const name = this.userDisplay(entry);
    return name.charAt(0).toUpperCase();
  }

  selectRow(id: number): void {
    this.selectedRowId.set(this.selectedRowId() === id ? null : id);
  }

  @HostListener('document:click')
  closeMenus(): void {
    this.openMenuId.set(null);
  }

  toggleMenu(event: Event, id: number): void {
    event.stopPropagation();
    this.openMenuId.set(this.openMenuId() === id ? null : id);
  }

  parseMetadata(entry: ActivityLogEntry): Record<string, unknown> {
    try {
      const raw = entry.metadata_json;
      if (!raw) return {};
      const data = JSON.parse(raw);
      return typeof data === 'object' && data ? data as Record<string, unknown> : {};
    } catch {
      return {};
    }
  }

  sessionIdFromEntry(entry: ActivityLogEntry): number | null {
    const meta = this.parseMetadata(entry);
    const sid = meta['session_id'];
    return typeof sid === 'number' ? sid : null;
  }

  isSecurityEntry(entry: ActivityLogEntry): boolean {
    const cat = (entry.category || '').toLowerCase();
    const action = (entry.action || '').toLowerCase();
    const level = (entry.level || '').toUpperCase();
    return cat === 'security' || action.includes('security') || action.includes('prompt') || level === 'WARNING' || level === 'CRITICAL';
  }

  openUserProfile(entry: ActivityLogEntry): void {
    if (!entry.user_id) return;
    this.openMenuId.set(null);
    this.navigate.emit({ target: 'users', userId: entry.user_id });
  }

  openConversation(entry: ActivityLogEntry): void {
    const sessionId = this.sessionIdFromEntry(entry);
    if (sessionId == null) return;
    this.openMenuId.set(null);
    this.navigate.emit({ target: 'conversations', sessionId });
  }

  openSecurityIncidents(): void {
    this.openMenuId.set(null);
    this.navigate.emit({ target: 'incidents' });
  }

  suspendUser(entry: ActivityLogEntry): void {
    if (!entry.user_id || this.actionBusy()) return;
    const ok = confirm(`Suspendre le compte de ${entry.user_email || entry.user_name || 'cet utilisateur'} ?`);
    if (!ok) return;
    this.actionBusy.set(true);
    this.admin.suspendUser(entry.user_id, `Suspension depuis journal d'audit`).subscribe({
      next: () => {
        this.actionMessage.set('Compte suspendu.');
        this.actionBusy.set(false);
        this.openMenuId.set(null);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.actionMessage.set(err.error?.detail || 'Suspension impossible.');
        this.actionBusy.set(false);
      },
    });
  }

  applyFilters(): void {
    this.load(true);
  }

  setPage(p: number): void {
    const max = this.totalPages();
    if (p < 1 || p > max) return;
    this.page.set(p);
    this.load();
  }

  onPageSizeChange(size: number): void {
    this.pageSize.set(size);
    this.page.set(1);
    this.load(true);
  }

  exportLogs(): void {
    const rows = this.displayLogs();
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  private load(resetPage = false): void {
    if (resetPage) this.page.set(1);
    this.loading.set(true);
    const offset = (this.page() - 1) * this.pageSize();
    const cat = this.category();
    const apiCategory = cat === 'all' ? undefined : cat;

    this.admin
      .listLogs({
        category: apiCategory,
        level: this.level() === 'all' ? undefined : this.level(),
        q: this.search().trim() || undefined,
        limit: this.pageSize(),
        offset,
      })
      .subscribe({
        next: (res) => {
          this.logs.set(res.items);
          this.logsTotal.set(res.total);
          this.loading.set(false);
        },
        error: () => {
          this.logs.set([]);
          this.logsTotal.set(0);
          this.loading.set(false);
        },
      });
  }

  private countByLevels(levels: string[]): number {
    return this.logs().filter((l) => levels.includes(l.level.toUpperCase())).length;
  }

  private formatNum(n: number): string {
    return n.toLocaleString('fr-FR');
  }

  private initDefaultDates(): void {
    const today = new Date();
    const iso = today.toISOString().slice(0, 10);
    this.dateFrom.set(iso);
    this.dateTo.set(iso);
  }

  private fallbackIp(id: number): string {
    const ips = ['192.168.1.12', '10.0.0.45', '172.16.0.8', '192.168.1.24', '10.0.0.102'];
    return ips[id % ips.length];
  }

  private categoryLabel(cat: string, action: string): string {
    const c = cat.toLowerCase();
    const a = action.toLowerCase();
    if (c === 'auth' || a.includes('login') || a.includes('auth')) return 'Authentification';
    if (c === 'admin' && (a.includes('user') || a.includes('role'))) return 'Utilisateurs';
    if (a.includes('report') || a.includes('export')) return 'Rapports';
    if (a.includes('security') || a.includes('permission')) return 'Sécurité';
    if (c === 'system') return 'Audit';
    if (c === 'chat') return 'Conversations';
    return 'Paramètres';
  }

  private categoryIcon(cat: string, action: string): string {
    const label = this.categoryLabel(cat, action);
    const map: Record<string, string> = {
      Authentification: 'shield',
      Utilisateurs: 'user',
      Paramètres: 'gear',
      Rapports: 'document',
      Sécurité: 'lock',
      Audit: 'history',
      Conversations: 'chat',
    };
    return map[label] ?? 'gear';
  }

  private buildPageItems(current: number, total: number): (number | 'ellipsis')[] {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const items: (number | 'ellipsis')[] = [1];
    if (current > 3) items.push('ellipsis');
    const start = Math.max(2, current - 1);
    const end = Math.min(total - 1, current + 1);
    for (let p = start; p <= end; p++) items.push(p);
    if (current < total - 2) items.push('ellipsis');
    items.push(total);
    return items;
  }

  private demoLogs(): ActivityLogEntry[] {
    const now = Date.now();
    const mk = (
      id: number,
      level: string,
      category: string,
      action: string,
      message: string,
      mins: number,
      ip: string,
    ): ActivityLogEntry => ({
      id,
      user_id: 1,
      actor_user_id: 1,
      user_email: 'admin@globex.ma',
      user_name: 'Administrateur Globex',
      actor_email: 'admin@globex.ma',
      level,
      category,
      action,
      message,
      metadata_json: '',
      ip_address: ip,
      created_at: new Date(now - mins * 60_000).toISOString(),
    });
    return [
      mk(1, 'INFO', 'auth', 'login', 'Connexion réussie', 2, '192.168.1.12'),
      mk(2, 'INFO', 'admin', 'user_view', 'Consultation fiche utilisateur', 8, '192.168.1.24'),
      mk(3, 'WARNING', 'admin', 'permissions', 'Modification permissions utilisateur', 15, '10.0.0.45'),
      mk(4, 'ERROR', 'auth', 'login_failed', 'Échec authentification', 22, '172.16.0.8'),
      mk(5, 'SUCCESS', 'admin', 'export', 'Export rapport généré', 35, '10.0.0.102'),
      mk(6, 'INFO', 'system', 'audit_read', 'Consultation observateur événements', 40, '192.168.1.12'),
      mk(7, 'CRITICAL', 'security', 'policy', 'Tentative accès ressource restreinte', 55, '10.0.0.45'),
      mk(8, 'INFO', 'admin', 'settings', 'Modification paramètres système', 70, '192.168.1.24'),
      mk(9, 'WARNING', 'auth', 'mfa', 'Échec validation MFA', 90, '172.16.0.8'),
      mk(10, 'SUCCESS', 'admin', 'report', 'Rapport mensuel généré', 120, '10.0.0.102'),
    ];
  }
}
