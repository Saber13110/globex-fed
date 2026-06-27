import { CommonModule, DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, OnInit, Output, SimpleChanges, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  AdminService,
  AdminUser,
  AdminUserDetail,
  ActivityLogEntry,
} from '../../../../core/services/admin.service';

type RoleFilter = 'all' | 'client' | 'employe' | 'admin';
type StatusFilter = 'all' | 'active' | 'pending' | 'invited' | 'suspended';
type SortKey = 'name' | 'role' | 'status' | 'created' | 'activity';
type DrawerTab = 'overview' | 'permissions' | 'activity' | 'sessions';

interface UserKpi {
  label: string;
  value: number;
  icon: string;
  tone: 'purple' | 'green' | 'orange' | 'blue';
  sparkline: number[];
}

interface ChartPoint {
  name: string;
  value: number;
}

interface RoleLegendItem {
  key: string;
  label: string;
  value: number;
  percent: number;
  color: string;
}

interface LocationBarItem {
  name: string;
  value: number;
  percent: number;
}

const ROLE_CHART_COLORS = ['#6d28ff', '#8b5cf6', '#a855f7', '#c084fc', '#22c55e', '#3b82f6'];

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, MatSnackBarModule],
  templateUrl: './admin-users.component.html',
  styleUrl: './admin-users.component.scss',
})
export class AdminUsersComponent implements OnInit, OnChanges {
  @Input() initialRoleFilter: RoleFilter = 'all';
  @Input() initialUserId: number | null = null;
  @Output() initialUserHandled = new EventEmitter<void>();

  readonly loading = signal(true);
  readonly users = signal<AdminUser[]>([]);
  readonly lastSync = signal<Date | null>(null);
  readonly search = signal('');
  readonly roleFilter = signal<RoleFilter>('all');
  readonly statusFilter = signal<StatusFilter>('all');
  readonly sortKey = signal<SortKey>('activity');
  readonly sortDir = signal<'asc' | 'desc'>('desc');
  readonly pageSize = signal(12);
  readonly page = signal(1);
  readonly filtersOpen = signal(false);
  readonly drawerTab = signal<DrawerTab>('overview');
  readonly selectedId = signal<number | null>(null);
  readonly detail = signal<AdminUserDetail | null>(null);
  readonly detailLoading = signal(false);
  readonly detailSaving = signal(false);
  readonly detailError = signal<string | null>(null);
  readonly detailSuccess = signal<string | null>(null);
  readonly activityLogs = signal<ActivityLogEntry[]>([]);
  readonly globalActivity = signal<ActivityLogEntry[]>([]);
  readonly globalActivityLoading = signal(false);
  readonly activityLoading = signal(false);
  readonly editing = signal(false);
  readonly inviteOpen = signal(false);
  readonly inviteLoading = signal(false);
  readonly inviteError = signal<string | null>(null);

  inviteFullName = '';
  inviteEmail = '';
  inviteRole = 'employe';
  userEditFullName = '';
  userEditRole = 'client';
  userEditStatus = 'active';
  userEditLang = 'fr';

  readonly drawerTabs: { id: DrawerTab; label: string }[] = [
    { id: 'overview', label: 'Profil' },
    { id: 'permissions', label: 'Permissions' },
    { id: 'activity', label: 'Activité' },
    { id: 'sessions', label: 'Sessions' },
  ];

  readonly roleFilterOptions = [
    { value: 'all' as const, label: 'Tous' },
    { value: 'admin' as const, label: 'Admins' },
    { value: 'employe' as const, label: 'Employés' },
    { value: 'client' as const, label: 'Clients' },
  ];

  readonly statusFilterOptions = [
    { value: 'all' as const, label: 'Tous' },
    { value: 'active' as const, label: 'Actifs' },
    { value: 'pending' as const, label: 'En attente' },
    { value: 'invited' as const, label: 'Invités' },
    { value: 'suspended' as const, label: 'Suspendus' },
  ];

  readonly sortOptions = [
    { value: 'activity' as SortKey, label: 'Activité' },
    { value: 'name' as SortKey, label: 'Nom' },
    { value: 'role' as SortKey, label: 'Rôle' },
    { value: 'status' as SortKey, label: 'Statut' },
    { value: 'created' as SortKey, label: 'Création' },
  ];

  readonly filteredUsers = computed(() => {
    const q = this.search().trim().toLowerCase();
    const role = this.roleFilter();
    const status = this.statusFilter();
    let rows = this.users().filter((u) => {
      if (role !== 'all' && u.role !== role) return false;
      if (status !== 'all' && u.status !== status) return false;
      if (!q) return true;
      return (
        u.full_name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        u.role.toLowerCase().includes(q) ||
        (u.last_location ?? '').toLowerCase().includes(q)
      );
    });

    const key = this.sortKey();
    const dir = this.sortDir() === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      switch (key) {
        case 'name':
          return a.full_name.localeCompare(b.full_name) * dir;
        case 'role':
          return a.role.localeCompare(b.role) * dir;
        case 'status':
          return a.status.localeCompare(b.status) * dir;
        case 'created':
          return (Date.parse(a.created_at) - Date.parse(b.created_at)) * dir;
        case 'activity':
        default:
          return (this.activityScore(a) - this.activityScore(b)) * dir;
      }
    });
    return rows;
  });

  readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredUsers().length / this.pageSize())),
  );

  readonly pagedUsers = computed(() => {
    const start = (this.page() - 1) * this.pageSize();
    return this.filteredUsers().slice(start, start + this.pageSize());
  });

  readonly selectedUser = computed(() => {
    const id = this.selectedId();
    return this.users().find((u) => u.id === id) ?? null;
  });

  readonly onlineCount = computed(() => this.users().filter((u) => u.is_online).length);

  readonly pendingInvites = computed(
    () => this.users().filter((u) => u.status === 'invited' || u.status === 'pending').length,
  );

  readonly kpis = computed((): UserKpi[] => {
    const all = this.users();
    const admins = all.filter((u) => u.role === 'admin').length;
    const online = this.onlineCount();
    const pending = this.pendingInvites();
    const history = this.buildSparkHistory(all.length);
    return [
      {
        label: 'Total Users',
        value: all.length,
        icon: 'users',
        tone: 'purple',
        sparkline: history,
      },
      {
        label: 'Online Users',
        value: online,
        icon: 'online',
        tone: 'green',
        sparkline: this.buildSparkHistory(online),
      },
      {
        label: 'Administrators',
        value: admins,
        icon: 'shield',
        tone: 'orange',
        sparkline: this.buildSparkHistory(admins),
      },
      {
        label: 'Pending Invitations',
        value: pending,
        icon: 'invite',
        tone: 'blue',
        sparkline: this.buildSparkHistory(pending),
      },
    ];
  });

  readonly roleChart = computed((): ChartPoint[] => {
    const counts: Record<string, number> = {};
    for (const u of this.users()) {
      counts[u.role] = (counts[u.role] ?? 0) + 1;
    }
    return Object.entries(counts).map(([role, value]) => ({
      name: this.roleLabel(role),
      value,
    }));
  });

  readonly roleLegend = computed((): RoleLegendItem[] => {
    const data = this.roleChart();
    const total = data.reduce((sum, d) => sum + d.value, 0) || 1;
    return data.map((d, i) => ({
      key: d.name,
      label: d.name,
      value: d.value,
      percent: Math.round((d.value / total) * 100),
      color: ROLE_CHART_COLORS[i % ROLE_CHART_COLORS.length],
    }));
  });

  readonly roleDonutGradient = computed(() => {
    const items = this.roleLegend();
    if (!items.length) return 'conic-gradient(#e2e8f0 0 100%)';
    let acc = 0;
    const stops = items.map((item) => {
      const start = acc;
      acc += item.percent;
      return `${item.color} ${start}% ${Math.min(acc, 100)}%`;
    });
    return `conic-gradient(${stops.join(', ')})`;
  });

  readonly locationChart = computed((): LocationBarItem[] => {
    const counts: Record<string, number> = {};
    let unknown = 0;
    for (const u of this.users()) {
      const label = this.locationLabelFromUser(u.last_location);
      if (!label) {
        unknown += 1;
        continue;
      }
      counts[label] = (counts[label] ?? 0) + 1;
    }
    if (unknown > 0) {
      counts['Non renseigné'] = (counts['Non renseigné'] ?? 0) + unknown;
    }
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
    const max = entries[0]?.[1] ?? 1;
    return entries.map(([name, value]) => ({
      name,
      value,
      percent: Math.max(8, Math.round((value / max) * 100)),
    }));
  });

  readonly topActiveUsers = computed(() =>
    [...this.users()]
      .sort((a, b) => this.activityScore(b) - this.activityScore(a))
      .slice(0, 5),
  );

  readonly avgActivityScore = computed(() => {
    const all = this.users();
    if (!all.length) return 0;
    const total = all.reduce((sum, u) => sum + this.activityScore(u), 0);
    return Math.round(total / all.length);
  });

  constructor(
    private readonly admin: AdminService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.roleFilter.set(this.initialRoleFilter);
    this.loadUsers();
    this.loadGlobalActivity();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['initialUserId'] && this.initialUserId != null) {
      this.tryOpenInitialUser(this.initialUserId);
    }
  }

  private tryOpenInitialUser(userId: number): void {
    const user = this.users().find((u) => u.id === userId);
    if (user) {
      this.selectUser(user);
      this.initialUserHandled.emit();
      return;
    }
    this.admin.getUserDetail(userId).subscribe({
      next: (detail) => {
        const stub: AdminUser = {
          id: detail.id,
          full_name: detail.full_name,
          email: detail.email,
          role: detail.role,
          status: detail.status,
          organization_id: detail.organization_id,
          preferred_language: detail.preferred_language,
          created_at: detail.created_at,
          last_activity_at: detail.last_activity_at,
          last_location: detail.last_location,
          is_online: detail.is_online,
          messages_count: detail.messages_count,
          trackings_count: detail.trackings_count,
        };
        this.selectUser(stub);
        this.initialUserHandled.emit();
      },
      error: () => this.initialUserHandled.emit(),
    });
  }

  loadUsers(): void {
    this.loading.set(true);
    this.admin.listUsers().subscribe({
      next: (rows) => {
        this.users.set(rows);
        this.lastSync.set(new Date());
        this.loading.set(false);
        if (this.initialUserId != null) {
          this.tryOpenInitialUser(this.initialUserId);
        }
      },
      error: () => {
        this.users.set([]);
        this.loading.set(false);
        this.snack.open('Impossible de charger les utilisateurs.', 'Fermer', {
          duration: 5000,
          panelClass: 'set-snack--err',
          horizontalPosition: 'end',
          verticalPosition: 'top',
        });
      },
    });
  }

  loadGlobalActivity(): void {
    this.globalActivityLoading.set(true);
    this.admin.listLogs({ limit: 14, offset: 0 }).subscribe({
      next: (res) => {
        this.globalActivity.set(res.items);
        this.globalActivityLoading.set(false);
      },
      error: () => this.globalActivityLoading.set(false),
    });
  }

  selectUser(user: AdminUser): void {
    this.selectedId.set(user.id);
    this.drawerTab.set('overview');
    this.detailError.set(null);
    this.detailSuccess.set(null);
    this.editing.set(false);
    this.loadDetail(user.id);
  }

  closeDrawer(): void {
    this.selectedId.set(null);
    this.detail.set(null);
    this.detailError.set(null);
    this.detailSuccess.set(null);
    this.editing.set(false);
  }

  setDrawerTab(tab: DrawerTab): void {
    this.drawerTab.set(tab);
    if (tab === 'activity') {
      this.loadActivity();
    }
  }

  setPage(p: number): void {
    const max = this.totalPages();
    this.page.set(Math.min(Math.max(1, p), max));
  }

  prevPage(): void {
    this.setPage(this.page() - 1);
  }

  nextPage(): void {
    this.setPage(this.page() + 1);
  }

  toggleSort(key: SortKey): void {
    if (this.sortKey() === key) {
      this.sortDir.set(this.sortDir() === 'asc' ? 'desc' : 'asc');
    } else {
      this.sortKey.set(key);
      this.sortDir.set(key === 'name' ? 'asc' : 'desc');
    }
    this.page.set(1);
  }

  openInvite(): void {
    this.inviteError.set(null);
    this.inviteFullName = '';
    this.inviteEmail = '';
    this.inviteRole = 'employe';
    this.inviteOpen.set(true);
  }

  closeInvite(): void {
    this.inviteOpen.set(false);
    this.inviteError.set(null);
  }

  submitInvite(): void {
    const name = this.inviteFullName.trim();
    const email = this.inviteEmail.trim();
    if (!name || !email) {
      this.inviteError.set('Nom et email requis.');
      return;
    }
    this.inviteLoading.set(true);
    this.inviteError.set(null);
    this.admin.inviteUser({ full_name: name, email, role: this.inviteRole }).subscribe({
      next: (res) => {
        this.inviteLoading.set(false);
        this.inviteOpen.set(false);
        this.snack.open(res.message, 'Fermer', {
          duration: 5000,
          panelClass: 'set-snack--ok',
          horizontalPosition: 'end',
          verticalPosition: 'top',
        });
        this.loadUsers();
        this.loadGlobalActivity();
      },
      error: (err: HttpErrorResponse) => {
        this.inviteLoading.set(false);
        this.inviteError.set(
          typeof err.error?.detail === 'string' ? err.error.detail : "Échec de l'invitation.",
        );
      },
    });
  }

  openEditUser(): void {
    const user = this.selectedUser();
    if (!user) return;
    this.detailError.set(null);
    this.detailSuccess.set(null);
    this.userEditFullName = user.full_name;
    this.userEditRole = user.role;
    this.userEditStatus = user.status;
    this.userEditLang = this.detail()?.preferred_language ?? user.preferred_language;
    this.editing.set(true);
    this.drawerTab.set('overview');
  }

  cancelEdit(): void {
    this.editing.set(false);
    const user = this.selectedUser();
    if (user) {
      this.userEditFullName = user.full_name;
      this.userEditRole = user.role;
      this.userEditStatus = user.status;
    }
  }

  confirmEdit(): void {
    this.saveUser();
  }

  saveUser(): void {
    const id = this.selectedId();
    if (id == null) return;
    this.detailSaving.set(true);
    this.detailError.set(null);
    this.admin
      .updateUser(id, {
        full_name: this.userEditFullName.trim(),
        role: this.userEditRole,
        status: this.userEditStatus,
        preferred_language: this.userEditLang,
      })
      .subscribe({
        next: (d) => {
          this.detail.set(d);
          this.detailSaving.set(false);
          this.editing.set(false);
          this.detailSuccess.set('Utilisateur mis à jour.');
          this.loadUsers();
          this.loadGlobalActivity();
        },
        error: (err: HttpErrorResponse) => {
          this.detailSaving.set(false);
          this.detailError.set(
            typeof err.error?.detail === 'string' ? err.error.detail : 'Échec de la sauvegarde.',
          );
        },
      });
  }

  toggleUserStatus(): void {
    const id = this.selectedId();
    const user = this.selectedUser();
    if (id == null || !user) return;

    if (user.status === 'suspended') {
      if (!confirm(`Réactiver le compte de ${user.full_name} ?`)) return;
      this.detailSaving.set(true);
      this.detailError.set(null);
      this.admin.reactivateUser(id).subscribe({
        next: () => this.reloadUserAfterStatusChange(id, 'Compte réactivé.'),
        error: (err: HttpErrorResponse) => this.onStatusChangeError(err),
      });
      return;
    }

    if (user.status === 'active') {
      if (!confirm(`Suspendre le compte de ${user.full_name} ? L'utilisateur ne pourra plus utiliser le chat ni l'agent IA.`)) return;
      this.detailSaving.set(true);
      this.detailError.set(null);
      this.admin.suspendUser(id, `Suspension manuelle depuis gestion utilisateurs`).subscribe({
        next: () => this.reloadUserAfterStatusChange(id, 'Compte suspendu.'),
        error: (err: HttpErrorResponse) => this.onStatusChangeError(err),
      });
      return;
    }

    if (!confirm(`Activer le compte de ${user.full_name} ?`)) return;
    this.detailSaving.set(true);
    this.detailError.set(null);
    this.admin.updateUser(id, { status: 'active' }).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.detailSaving.set(false);
        this.detailSuccess.set('Compte activé.');
        this.loadUsers();
      },
      error: (err: HttpErrorResponse) => this.onStatusChangeError(err),
    });
  }

  private reloadUserAfterStatusChange(id: number, message: string): void {
    this.admin.getUserDetail(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.detailSaving.set(false);
        this.detailSuccess.set(message);
        this.loadUsers();
      },
      error: () => {
        this.detailSaving.set(false);
        this.detailSuccess.set(message);
        this.loadUsers();
      },
    });
  }

  private onStatusChangeError(err: HttpErrorResponse): void {
    this.detailSaving.set(false);
    this.detailError.set(
      typeof err.error?.detail === 'string' ? err.error.detail : 'Échec de la mise à jour du statut.',
    );
  }

  /** @deprecated use toggleUserStatus */
  deactivateUser(): void {
    this.toggleUserStatus();
  }

  deleteUser(): void {
    const user = this.selectedUser();
    const id = this.selectedId();
    if (!user || id == null) return;
    if (!confirm(`Supprimer définitivement ${user.full_name} ? Cette action est irréversible.`)) return;
    this.detailSaving.set(true);
    this.detailError.set(null);
    this.admin.deleteUser(id).subscribe({
      next: () => {
        this.detailSaving.set(false);
        this.closeDrawer();
        this.loadUsers();
        this.loadGlobalActivity();
        this.snack.open('Utilisateur supprimé.', 'Fermer', {
          duration: 4000,
          horizontalPosition: 'end',
          verticalPosition: 'top',
          panelClass: 'set-snack--ok',
        });
      },
      error: (err: HttpErrorResponse) => {
        this.detailSaving.set(false);
        this.detailError.set(
          typeof err.error?.detail === 'string' ? err.error.detail : 'Suppression impossible.',
        );
      },
    });
  }

  messageUser(user: AdminUser): void {
    window.location.href = `mailto:${user.email}`;
  }

  viewLogs(user: AdminUser): void {
    this.selectUser(user);
    this.setDrawerTab('activity');
  }

  viewPermissions(user: AdminUser): void {
    this.selectUser(user);
    this.setDrawerTab('permissions');
  }

  userInitial(name: string): string {
    const trimmed = name.trim();
    return trimmed ? trimmed.charAt(0).toUpperCase() : '?';
  }

  initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  roleBadgeClass(role: string): string {
    if (role === 'admin') return 'um-badge--admin';
    if (role === 'employe') return 'um-badge--employe';
    return 'um-badge--client';
  }

  statusActionLabel(status: string): string {
    if (status === 'suspended') return 'Réactiver';
    if (status === 'active') return 'Suspendre';
    return 'Activer';
  }

  roleLabel(role: string): string {
    const map: Record<string, string> = {
      admin: 'Administrateur',
      employe: 'Employé',
      client: 'Client',
    };
    return map[role] ?? role;
  }

  roleTitle(role: string): string {
    const map: Record<string, string> = {
      admin: 'Platform Administrator',
      employe: 'Operations Specialist',
      client: 'Customer Account',
    };
    return map[role] ?? role;
  }

  statusLabel(status: string): string {
    const map: Record<string, string> = {
      active: 'Actif',
      pending: 'En attente',
      invited: 'Invité',
      suspended: 'Suspendu',
    };
    return map[status] ?? status;
  }

  statusBadgeClass(status: string): string {
    if (status === 'active') return 'um-status--active';
    if (status === 'pending') return 'um-status--pending';
    if (status === 'suspended') return 'um-status--suspended';
    return 'um-status--invited';
  }

  permissionsForRole(role: string): string[] {
    if (role === 'admin') {
      return ['Tracking', 'Reports', 'AI Assistant', 'Users', 'Audit', 'Settings'];
    }
    if (role === 'employe') {
      return ['Tracking', 'Reports', 'AI Assistant'];
    }
    return ['Tracking'];
  }

  countryFromLocation(location?: string | null): string | null {
    return this.locationLabelFromUser(location);
  }

  locationLabelFromUser(location?: string | null): string | null {
    if (!location || location === 'Unknown') return null;
    const trimmed = location.trim();
    if (this.isIpLike(trimmed)) return null;

    const parts = trimmed.split(',').map((p) => p.trim()).filter(Boolean);
    if (!parts.length) return null;

    const last = parts[parts.length - 1];
    if (this.isIpLike(last)) {
      return parts[0] && !this.isIpLike(parts[0]) ? parts[0] : null;
    }
    return last;
  }

  private isIpLike(value: string): boolean {
    const v = value.trim().toLowerCase();
    if (v === 'localhost' || v === 'unknown') return true;
    return /^\d{1,3}(\.\d{1,3}){3}(:\d+)?$/.test(v);
  }

  cityFromLocation(location?: string | null): string | null {
    if (!location || location === 'Unknown') return null;
    const parts = location.split(',').map((p) => p.trim()).filter(Boolean);
    return parts[0] ?? location;
  }

  activityScore(user: AdminUser): number {
    const msgs = user.messages_count ?? 0;
    const tracks = user.trackings_count ?? 0;
    const online = user.is_online ? 15 : 0;
    const recent = user.last_activity_at
      ? Math.max(0, 20 - Math.floor((Date.now() - Date.parse(user.last_activity_at)) / 86400000))
      : 0;
    return msgs + tracks * 2 + online + recent;
  }

  relativeTime(iso?: string | null): string {
    if (!iso) return 'Jamais';
    const diff = Date.now() - Date.parse(iso);
    if (Number.isNaN(diff) || diff < 0) return '—';
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "À l'instant";
    if (mins < 60) return `Il y a ${mins} min`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `Il y a ${hours} h`;
    const days = Math.floor(hours / 24);
    if (days === 1) return 'Hier';
    if (days < 7) return `Il y a ${days} j`;
    return new Date(iso).toLocaleDateString('fr-FR');
  }

  formatDate(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  activityIcon(action: string): string {
    if (action.includes('invite') || action.includes('user')) return 'user';
    if (action.includes('ai') || action.includes('chat')) return 'ai';
    if (action.includes('track') || action.includes('shipment')) return 'shipment';
    if (action.includes('permission') || action.includes('role')) return 'shield';
    if (action.includes('report')) return 'report';
    return 'dot';
  }

  activityLabel(log: ActivityLogEntry): string {
    const who = log.user_name ?? log.actor_email ?? 'Utilisateur';
    if (log.action.includes('invite')) return `${who} a été invité`;
    if (log.action.includes('user_view')) return `Profil consulté — ${log.user_email ?? who}`;
    if (log.action.includes('ai')) return `${who} — requête IA`;
    if (log.action.includes('track')) return `${who} — suivi colis`;
    if (log.action.includes('permission') || log.action.includes('role')) return `Permissions mises à jour — ${who}`;
    if (log.action.includes('report')) return `${who} — rapport généré`;
    return log.message;
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

  private buildSparkHistory(current: number): number[] {
    const base = Math.max(current - 3, 0);
    return [base, base + 1, Math.max(base, current - 1), current, current, current, current];
  }

  private loadDetail(id: number): void {
    this.detailLoading.set(true);
    this.admin.getUserDetail(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.userEditFullName = d.full_name;
        this.userEditRole = d.role;
        this.userEditStatus = d.status;
        this.userEditLang = d.preferred_language;
        this.detailLoading.set(false);
      },
      error: () => this.detailLoading.set(false),
    });
  }

  private loadActivity(): void {
    const id = this.selectedId();
    if (id == null) return;
    this.activityLoading.set(true);
    this.admin.listLogs({ user_id: id, limit: 20, offset: 0 }).subscribe({
      next: (res) => {
        this.activityLogs.set(res.items);
        this.activityLoading.set(false);
      },
      error: () => this.activityLoading.set(false),
    });
  }
}
