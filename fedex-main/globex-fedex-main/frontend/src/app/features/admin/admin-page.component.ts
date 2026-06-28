import { CommonModule, DatePipe } from '@angular/common';
import { Component, HostBinding, HostListener, Input, OnDestroy, OnInit, computed, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';

import {
  AdminDashboardStats,
  AdminService,
  AdminUser,
  AdminUserDetail,
  PreferenceProfileStructured,
  PreferenceSubmission,
} from '../../core/services/admin.service';
import { AuthService } from '../../core/services/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { LangCode } from '../../core/i18n/i18n.types';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import { API_BASE_URL, JARVIS_UI_URL } from '../../core/api.config';
import { CommandCenterPayload, CommandCenterService, DashboardNavEvent } from '../../core/services/command-center.service';
import { NotificationsService, NotificationItem } from '../../core/services/notifications.service';
import { AssetPreloadService } from '../../core/services/asset-preload.service';
import { AdminEmployeeChatDrawerComponent } from './components/admin-employee-chat-drawer/admin-employee-chat-drawer.component';
import { AdminSupportDrawerComponent } from './components/admin-support-drawer/admin-support-drawer.component';
import { AdminDashboardComponent } from './components/admin-dashboard/admin-dashboard.component';
import { AdminConversationsComponent, ConvNavigateEvent } from './components/admin-conversations/admin-conversations.component';
import { AdminTrackingComponent } from './components/admin-tracking/admin-tracking.component';
import { AdminUsersComponent } from './components/admin-users/admin-users.component';
import { AdminAuditLogsComponent, AuditLogNavigateEvent } from './components/admin-audit-logs/admin-audit-logs.component';
import { AdminSupportTicketsComponent } from './components/admin-support-tickets/admin-support-tickets.component';
import { AdminSettingsComponent } from './components/admin-settings/admin-settings.component';
import { AdminReportsComponent } from './components/admin-reports/admin-reports.component';
import { AdminAiAssistantComponent } from './components/admin-ai-assistant/admin-ai-assistant.component';
import { AdminAiHealthComponent } from './components/admin-ai-health/admin-ai-health.component';
import { AdminGptKnowledgeComponent } from './components/admin-gpt-knowledge/admin-gpt-knowledge.component';
import { AdminNotificationsComponent } from './components/admin-notifications/admin-notifications.component';
import { AdminSecurityComponent } from './components/admin-security/admin-security.component';

type AdminTab = 'overview' | 'logs' | 'users' | 'user' | 'preferences' | 'conversations' | 'tracking';
export type AdminSection =
  | 'dashboard'
  | 'ai-assistant'
  | 'ai-health'
  | 'gpt-knowledge'
  | 'conversations'
  | 'analytics'
  | 'users'
  | 'roles'
  | 'reports'
  | 'tracking'
  | 'incidents'
  | 'notifications'
  | 'monitoring'
  | 'audit-logs'
  | 'settings'
  | 'agent-missions';

@Component({
  selector: 'app-admin-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    RouterOutlet,
    DatePipe,
    TranslatePipe,
    AdminDashboardComponent,
    AdminConversationsComponent,
    AdminTrackingComponent,
    AdminUsersComponent,
    AdminAuditLogsComponent,
    AdminSupportTicketsComponent,
    AdminSettingsComponent,
    AdminReportsComponent,
    AdminAiAssistantComponent,
    AdminAiHealthComponent,
    AdminGptKnowledgeComponent,
    AdminNotificationsComponent,
    AdminSecurityComponent,
    AdminSupportDrawerComponent,
    AdminEmployeeChatDrawerComponent,
  ],
  templateUrl: './admin-page.component.html',
  styleUrl: './admin-page.component.scss',
})
export class AdminPageComponent implements OnInit, OnDestroy {
  @HostBinding('class.admin--rtl') get adminRtl(): boolean {
    return this.i18n.isRtl();
  }

  readonly activeSection = signal<AdminSection>('dashboard');
  readonly agentMissionsActive = signal(false);
  readonly activeTab = signal<AdminTab>('overview');
  readonly globalSearch = signal('');
  readonly auditLogSearch = signal('');
  readonly trackingSearch = signal('');
  readonly trackingShipmentId = signal<number | null>(null);
  readonly dashboardConversationId = signal<number | null>(null);
  readonly usersInitialRole = signal<'all' | 'client' | 'employe' | 'admin'>('all');
  readonly usersInitialUserId = signal<number | null>(null);
  readonly adminDisplayName = signal('Administrator Globex');
  readonly adminEmail = signal('');
  readonly adminInitial = computed(() => {
    const name = this.adminDisplayName().trim();
    return name ? name.charAt(0).toUpperCase() : 'A';
  });
  readonly ccData = signal<CommandCenterPayload | null>(null);

  readonly users = signal<AdminUser[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly dashboard = signal<AdminDashboardStats | null>(null);
  readonly dashboardLoading = signal(true);

  readonly pending = signal<AdminUser[]>([]);
  readonly pendingError = signal<string | null>(null);
  readonly pendingSuccess = signal<string | null>(null);
  readonly busyId = signal<number | null>(null);

  readonly userSearch = signal('');
  readonly userRoleFilter = signal<'all' | 'client' | 'employe' | 'admin'>('all');
  readonly userStatusFilter = signal<'all' | 'pending' | 'invited' | 'active'>('all');

  readonly filteredUsers = computed(() => {
    const q = this.userSearch().trim().toLowerCase();
    const role = this.userRoleFilter();
    const status = this.userStatusFilter();
    return this.users().filter((u) => {
      if (role !== 'all' && u.role !== role) return false;
      if (status !== 'all' && u.status !== status) return false;
      if (!q) return true;
      return u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
    });
  });

  readonly preferenceSubmissions = signal<PreferenceSubmission[]>([]);
  readonly preferencesLoading = signal(false);
  readonly preferencesError = signal<string | null>(null);

  readonly platformNotifItems = signal<NotificationItem[]>([]);
  readonly notificationsLoading = signal(false);
  readonly notificationsOpen = signal(false);
  readonly hasFreshNotif = signal(false);
  readonly supportDrawerOpen = signal(false);
  readonly supportTicketId = signal<number | null>(null);
  readonly securityIncidentId = signal<number | null>(null);
  readonly employeeChatDrawerOpen = signal(false);
  readonly employeeChatId = signal<number | null>(null);
  readonly accountMenuOpen = signal(false);
  readonly accountMenuAnchor = signal<'header' | 'sidebar' | null>(null);
  readonly langMenuOpen = signal(false);
  readonly platformUnreadCount = signal(0);
  readonly notificationCount = computed(() => this.platformUnreadCount());

  private readonly subs = new Subscription();

  readonly selectedUserId = signal<number | null>(null);
  readonly userDetail = signal<AdminUserDetail | null>(null);
  readonly userDetailLoading = signal(false);
  readonly userDetailSaving = signal(false);
  readonly userDetailError = signal<string | null>(null);
  readonly userDetailSuccess = signal<string | null>(null);

  userEditFullName = '';
  userEditRole = 'client';
  userEditStatus = 'active';
  userEditLang = 'fr';
  userEditPrompt = '';
  /** null = illimité (envoi 0 à l'API) */
  userEditQuotaMessages: number | null = null;
  userEditQuotaTrackings: number | null = null;
  userEditQuotaExports: number | null = null;

  readonly navGroups = computed(() => {
    this.i18n.lang();
    return [
      {
        title: '',
        items: [
          { id: 'dashboard' as AdminSection, label: this.i18n.t('admin.nav.dashboard'), icon: 'grid' },
          { id: 'ai-assistant' as AdminSection, label: this.i18n.t('admin.nav.aiAssistant'), icon: 'sparkles' },
          { id: 'ai-health' as AdminSection, label: 'AI Health', icon: 'activity' },
          { id: 'gpt-knowledge' as AdminSection, label: 'Base connaissances GPT', icon: 'file' },
          { id: 'conversations' as AdminSection, label: this.i18n.t('admin.nav.conversations'), icon: 'message' },
        ],
      },
      {
        title: this.i18n.t('admin.nav.sectionOperations'),
        items: [
          { id: 'tracking' as AdminSection, label: this.i18n.t('admin.nav.tracking'), icon: 'truck' },
          { id: 'notifications' as AdminSection, label: this.i18n.t('admin.nav.notifications'), icon: 'bell' },
        ],
      },
      {
        title: this.i18n.t('admin.nav.sectionManagement'),
        items: [
          { id: 'users' as AdminSection, label: this.i18n.t('admin.nav.users'), icon: 'users' },
          { id: 'reports' as AdminSection, label: this.i18n.t('admin.nav.reports'), icon: 'file' },
          { id: 'agent-missions' as AdminSection, label: 'Agent Missions', icon: 'automation', route: '/admin/agent-missions' },
        ],
      },
      {
        title: this.i18n.t('admin.nav.sectionSystem'),
        items: [
          { id: 'audit-logs' as AdminSection, label: this.i18n.t('admin.nav.auditLogs'), icon: 'list' },
          { id: 'incidents' as AdminSection, label: this.i18n.t('admin.nav.security'), icon: 'shield' },
          { id: 'settings' as AdminSection, label: this.i18n.t('admin.nav.settings'), icon: 'settings' },
        ],
      },
    ];
  });

  readonly globalSearchPlaceholder = computed(() => {
    this.i18n.lang();
    const section = this.activeSection();
    if (section === 'conversations') {
      return this.i18n.t('admin.search.conversations');
    }
    if (section === 'users' || section === 'roles') {
      return this.i18n.t('admin.search.users');
    }
    return this.i18n.t('admin.search.default');
  });

  readonly lastLoginLabel = signal('Today');

  constructor(
    private readonly admin: AdminService,
    private readonly auth: AuthService,
    private readonly i18n: I18nService,
    private readonly commandCenter: CommandCenterService,
    private readonly notificationsApi: NotificationsService,
    private readonly assetPreload: AssetPreloadService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    localStorage.removeItem('globex_admin_sidebar');
    this.assetPreload.preloadAdminVisuals();
    this.refreshAll();
    this.loadPlatformNotifications();
    this.notificationsApi.startPolling(12_000);
    this.subs.add(
      this.notificationsApi.unread$.subscribe((count) => {
        this.platformUnreadCount.set(count);
      }),
    );
    this.subs.add(
      this.notificationsApi.freshPulse$.subscribe((pulse) => this.hasFreshNotif.set(pulse)),
    );
    this.auth.me().subscribe({
      next: (p) => {
        if (p.full_name) this.adminDisplayName.set(p.full_name);
        this.adminEmail.set(p.email);
        this.i18n.syncFromAuthProfile(p.preferred_language);
      },
    });
    this.commandCenter.getPayload().subscribe({
      next: (p) => this.ccData.set(p),
    });
    this.syncAgentMissionsRoute(this.router.url);
    this.subs.add(
      this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe((event) => {
        const nav = event as NavigationEnd;
        this.syncAgentMissionsRoute(nav.urlAfterRedirects || nav.url);
      }),
    );
    this.subs.add(
      this.route.queryParamMap.subscribe((params) => {
        const section = params.get('section');
        if (section) {
          this.setSection(section as AdminSection);
        }
        const ticket = params.get('ticket');
        if (ticket) {
          const id = Number(ticket);
          if (Number.isFinite(id) && id > 0) {
            this.supportTicketId.set(id);
            this.supportDrawerOpen.set(true);
          }
        }
        const employee = params.get('employee');
        if (employee) {
          const id = Number(employee);
          if (Number.isFinite(id) && id > 0) {
            this.setSection('conversations');
            this.employeeChatId.set(id);
            this.employeeChatDrawerOpen.set(true);
          }
        }
        const incident = params.get('incident');
        if (incident) {
          const id = Number(incident);
          if (Number.isFinite(id) && id > 0) {
            this.securityIncidentId.set(id);
            this.setSection('incidents');
          }
        }
      }),
    );
  }

  @HostListener('document:keydown', ['$event'])
  onKeydown(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      const el = document.getElementById('cc-global-search');
      el?.focus();
    }
  }

  openJarvisUi(): void {
    window.open(JARVIS_UI_URL, '_blank', 'noopener,noreferrer');
  }

  setSection(section: AdminSection): void {
    if (section === 'agent-missions') {
      void this.router.navigate(['/admin/agent-missions']);
      return;
    }
    if (this.agentMissionsActive()) {
      void this.router.navigate(['/admin']);
    }
    this.activeSection.set(section);
    if (section === 'notifications') {
      return;
    }
    if (section === 'dashboard' || section === 'analytics' || section === 'ai-assistant' || section === 'monitoring') {
      return;
    }
    if (section === 'users') {
      this.activeTab.set('users');
      this.userRoleFilter.set('all');
    } else if (section === 'roles') {
      this.activeTab.set('users');
      this.userRoleFilter.set('employe');
    } else if (section === 'audit-logs') {
      this.activeTab.set('logs');
    } else if (section === 'incidents') {
      this.activeTab.set('overview');
    } else if (section === 'settings') {
      this.activeTab.set('overview');
    } else if (section === 'conversations') {
      this.activeTab.set('conversations');
    } else if (section === 'tracking') {
      this.activeTab.set('tracking');
    } else if (section === 'reports') {
      this.activeTab.set('overview');
    }
  }

  private syncAgentMissionsRoute(url: string): void {
    const active = url.includes('/admin/agent-missions');
    this.agentMissionsActive.set(active);
    if (active) {
      this.activeSection.set('agent-missions');
    }
  }

  onDashboardNavigate(event: DashboardNavEvent): void {
    const map: Record<string, AdminSection> = {
      tracking: 'tracking',
      conversations: 'conversations',
      'audit-logs': 'audit-logs',
      reports: 'reports',
      users: 'users',
      notifications: 'notifications',
      'ai-assistant': 'ai-assistant',
      incidents: 'incidents',
      monitoring: 'monitoring',
      settings: 'settings',
    };

    if (event.trackingNumber?.trim()) {
      this.trackingSearch.set(event.trackingNumber.trim());
    } else if (event.target === 'tracking') {
      this.trackingSearch.set('');
    }

    if (event.shipmentId != null) {
      this.trackingShipmentId.set(event.shipmentId);
    } else if (event.target === 'tracking') {
      this.trackingShipmentId.set(null);
    }

    if (event.conversationId != null) {
      this.dashboardConversationId.set(event.conversationId);
    } else if (event.target === 'conversations') {
      this.dashboardConversationId.set(null);
    }

    if (event.roleKey) {
      this.usersInitialRole.set(event.roleKey);
    } else if (event.target === 'users') {
      this.usersInitialRole.set('all');
    }

    if (event.auditQuery?.trim()) {
      this.auditLogSearch.set(event.auditQuery.trim());
    } else if (event.target === 'audit-logs' && !event.auditQuery) {
      this.auditLogSearch.set('');
    }

    if (map[event.target]) this.setSection(map[event.target]);
  }

  onAuditNavigate(event: AuditLogNavigateEvent): void {
    if (event.target === 'users' && event.userId != null) {
      this.usersInitialRole.set('all');
      this.usersInitialUserId.set(event.userId);
      this.setSection('users');
      this.globalSearch.set(String(event.userId));
      return;
    }
    if (event.target === 'conversations' && event.sessionId != null) {
      this.dashboardConversationId.set(event.sessionId);
      this.setSection('conversations');
      return;
    }
    if (event.target === 'incidents' || event.target === 'security') {
      this.setSection('incidents');
    }
  }

  onConversationNavigate(event: ConvNavigateEvent): void {
    if (event.target === 'users') {
      this.usersInitialRole.set('all');
      this.usersInitialUserId.set(event.userId);
      this.setSection('users');
      return;
    }
    if (event.target === 'incidents') {
      this.setSection('incidents');
    }
  }

  applyGlobalSearch(): void {
    const q = this.globalSearch().trim().toLowerCase();
    if (!q) return;
    if (q.includes('user') || q.includes('utilisateur')) {
      this.setSection('users');
      this.userSearch.set(q.replace(/user|utilisateur/gi, '').trim());
      return;
    }
    if (q.includes('log') || q.includes('audit')) {
      this.auditLogSearch.set(q);
      this.setSection('audit-logs');
      return;
    }
    if (q.includes('ship') || q.includes('fedex') || q.includes('colis')) {
      this.setSection('tracking');
      return;
    }
    this.auditLogSearch.set(q);
    this.setSection('audit-logs');
  }

  exportReport(): void {
    const token = localStorage.getItem('globex_jwt');
    const url = `${API_BASE_URL}/export/tracking-history.xlsx`;
    if (!token) {
      window.open(url, '_blank');
      return;
    }
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => {
        if (!r.ok) throw new Error('export failed');
        return r.blob();
      })
      .then((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'tracking-history.xlsx';
        a.click();
        URL.revokeObjectURL(a.href);
      })
      .catch(() => {
        this.pendingError.set(this.i18n.t('admin.exportFailed'));
      });
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.notificationsApi.stopPolling();
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.notificationsOpen.set(false);
    this.accountMenuOpen.set(false);
    this.accountMenuAnchor.set(null);
    this.langMenuOpen.set(false);
  }

  toggleAccountMenu(event: MouseEvent, anchor: 'header' | 'sidebar'): void {
    event.stopPropagation();
    const sameAnchor = this.accountMenuOpen() && this.accountMenuAnchor() === anchor;
    if (sameAnchor) {
      this.accountMenuOpen.set(false);
      this.accountMenuAnchor.set(null);
      this.langMenuOpen.set(false);
      return;
    }
    this.accountMenuAnchor.set(anchor);
    this.accountMenuOpen.set(true);
  }

  toggleLangMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.langMenuOpen.update((v) => !v);
  }

  selectLanguage(code: LangCode, event: MouseEvent): void {
    event.stopPropagation();
    this.langMenuOpen.set(false);
    if (this.i18n.langCode() === code) {
      return;
    }
    this.i18n.setLang(code, true);
    if (this.auth.token()) {
      this.auth
        .updateProfile({ preferred_language: this.i18n.toBackendCode(code) })
        .subscribe({ error: () => undefined });
    }
  }

  isActiveLang(code: LangCode): boolean {
    return this.i18n.langCode() === code;
  }

  get languageOptions() {
    return this.i18n.languageOptions;
  }

  logoutFromMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.accountMenuOpen.set(false);
    this.accountMenuAnchor.set(null);
    this.langMenuOpen.set(false);
    this.logout();
  }

  toggleNotifications(event: MouseEvent): void {
    event.stopPropagation();
    const next = !this.notificationsOpen();
    this.notificationsOpen.set(next);
    if (next) {
      this.loadPlatformNotifications();
    }
  }

  loadPlatformNotifications(): void {
    this.notificationsLoading.set(true);
    this.notificationsApi.list({ page_size: 8, sort: 'newest' }).subscribe({
      next: (res) => {
        this.platformNotifItems.set(res.items);
        this.platformUnreadCount.set(res.unread_count);
        this.notificationsApi.setUnreadCount(res.unread_count);
        this.notificationsLoading.set(false);
      },
      error: () => this.notificationsLoading.set(false),
    });
  }

  openPlatformNotification(item: NotificationItem, event: MouseEvent): void {
    event.stopPropagation();
    if (!item.is_read) {
      this.notificationsApi.markRead(item.id).subscribe({
        next: () => {
          item.is_read = true;
          this.notificationsApi.setUnreadCount(Math.max(0, this.platformUnreadCount() - 1));
        },
      });
    }
    this.notificationsOpen.set(false);
    if (item.action_type === 'support_ticket') {
      const id = Number(item.action_ref);
      if (Number.isFinite(id) && id > 0) {
        this.supportTicketId.set(id);
        this.supportDrawerOpen.set(true);
      }
      return;
    }
    if (item.action_type === 'employee_chat') {
      const id = Number(item.action_ref);
      if (Number.isFinite(id) && id > 0) {
        this.setSection('conversations');
        this.employeeChatId.set(id);
        this.employeeChatDrawerOpen.set(true);
      }
      return;
    }
    if (item.action_type === 'security_suspend_user') {
      const uid = Number(item.action_ref);
      if (Number.isFinite(uid) && uid > 0) {
        const ok = confirm(
          `${item.title}\n\n${item.message}\n\nSuspendre ce compte maintenant ? L'utilisateur ne pourra plus utiliser le chat ni l'agent IA.`,
        );
        if (ok) {
          this.admin.suspendUser(uid, item.message).subscribe({
            next: () => {
              this.loadPlatformNotifications();
              this.notificationsApi.refreshUnread();
            },
            error: (err: HttpErrorResponse) => {
              alert(typeof err.error?.detail === 'string' ? err.error.detail : 'Suspension impossible.');
            },
          });
        }
      }
      return;
    }
    if (item.action_type === 'security_incident') {
      this.setSection('incidents');
      return;
    }
    this.setSection('notifications');
  }

  closeEmployeeChatDrawer(): void {
    this.employeeChatDrawerOpen.set(false);
    this.employeeChatId.set(null);
  }

  onEmployeeChatUpdated(): void {
    this.loadPlatformNotifications();
  }

  openUserTicketFromMessaging(ticketId: number): void {
    this.supportTicketId.set(ticketId);
    this.supportDrawerOpen.set(true);
  }

  closeSupportDrawer(): void {
    this.supportDrawerOpen.set(false);
    this.supportTicketId.set(null);
  }

  onSupportUpdated(): void {
    this.loadPlatformNotifications();
    this.notificationsApi.refreshUnread();
  }

  markAllPlatformRead(event: MouseEvent): void {
    event.stopPropagation();
    this.notificationsApi.markAllRead().subscribe({
      next: () => {
        this.platformNotifItems.update((items) => items.map((n) => ({ ...n, is_read: true })));
        this.notificationsApi.setUnreadCount(0);
      },
    });
  }

  viewAllPlatformNotifications(event: MouseEvent): void {
    event.stopPropagation();
    this.notificationsOpen.set(false);
    this.setSection('notifications');
  }

  onNotificationsNavigate(section: string): void {
    this.setSection(section as AdminSection);
  }

  onNotificationsUnread(count: number): void {
    this.platformUnreadCount.set(count);
    this.notificationsApi.setUnreadCount(count);
  }

  setTab(tab: AdminTab): void {
    this.activeTab.set(tab);
    if (tab === 'preferences') {
      this.loadPreferenceSubmissions();
    }
  }

  loadPreferenceSubmissions(): void {
    this.preferencesLoading.set(true);
    this.preferencesError.set(null);
    this.admin.listPendingPreferences().subscribe({
      next: (rows) => {
        this.preferenceSubmissions.set(rows);
        this.preferencesLoading.set(false);
      },
      error: () => {
        this.preferencesError.set(this.i18n.t('admin.prefsLoadError'));
        this.preferencesLoading.set(false);
      },
    });
  }

  approvePreference(sub: PreferenceSubmission): void {
    this.busyId.set(sub.id);
    this.admin.approvePreference(sub.id).subscribe({
      next: () => {
        this.busyId.set(null);
        this.loadPreferenceSubmissions();
        this.refreshAll();
        this.loadPlatformNotifications();
      },
      error: (err: HttpErrorResponse) => {
        this.busyId.set(null);
        this.preferencesError.set(
          typeof err.error?.detail === 'string' ? err.error.detail : this.i18n.t('admin.prefsApproveFailed'),
        );
      },
    });
  }

  rejectPreference(sub: PreferenceSubmission): void {
    this.admin.rejectPreference(sub.id).subscribe({
      next: () => {
        this.loadPreferenceSubmissions();
        this.loadPlatformNotifications();
      },
      error: () => this.preferencesError.set(this.i18n.t('admin.prefsRejectFailed')),
    });
  }

  formatStructured(profile: PreferenceProfileStructured | null | undefined): string {
    if (!profile) {
      return '';
    }
    const parts: string[] = [this.i18n.t(`settings.tone.${profile.tone}`)];
    if (profile.cite_fedex) {
      parts.push(this.i18n.t('settings.citeFedex'));
    }
    if (profile.short_answers) {
      parts.push(this.i18n.t('settings.shortAnswers'));
    }
    if (profile.free_notes?.trim()) {
      parts.push(profile.free_notes.trim());
    }
    return parts.join(' · ');
  }

  refreshAll(): void {
    this.loading.set(true);
    this.dashboardLoading.set(true);
    this.admin.getDashboard().subscribe({
      next: (s) => {
        this.dashboard.set(s);
        this.dashboardLoading.set(false);
      },
      error: () => this.dashboardLoading.set(false),
    });
    this.admin.listUsers().subscribe({
      next: (rows) => {
        this.users.set(rows);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(this.i18n.t('admin.loadUsersError'));
        this.loading.set(false);
      },
    });
    this.loadPending();
    this.notificationsApi.refreshUnread();
  }

  loadPending(): void {
    this.admin.listPendingEmployees().subscribe({
      next: (rows) => this.pending.set(rows),
      error: () => this.pendingError.set(this.i18n.t('admin.loadPendingError')),
    });
  }

  openUser(user: AdminUser): void {
    this.selectedUserId.set(user.id);
    this.activeTab.set('user');
    this.userDetailLoading.set(true);
    this.userDetailError.set(null);
    this.userDetailSuccess.set(null);
    this.admin.getUserDetail(user.id).subscribe({
      next: (detail) => {
        this.userDetail.set(detail);
        this.userEditFullName = detail.full_name;
        this.userEditRole = detail.role;
        this.userEditStatus = detail.status;
        this.userEditLang = detail.preferred_language;
        this.userEditPrompt = detail.response_preferences;
        const lim = detail.quotas?.limits;
        this.userEditQuotaMessages = lim?.messages_per_day ?? null;
        this.userEditQuotaTrackings = lim?.trackings_per_day ?? null;
        this.userEditQuotaExports = lim?.exports_per_day ?? null;
        this.userDetailLoading.set(false);
      },
      error: () => {
        this.userDetailError.set(this.i18n.t('admin.userLoadError'));
        this.userDetailLoading.set(false);
      },
    });
  }

  closeUser(): void {
    this.selectedUserId.set(null);
    this.userDetail.set(null);
    this.activeTab.set('users');
  }

  saveUserDetail(): void {
    const id = this.selectedUserId();
    if (id == null) return;
    this.userDetailSaving.set(true);
    this.userDetailError.set(null);
    this.userDetailSuccess.set(null);
    this.admin
      .updateUser(id, {
        full_name: this.userEditFullName.trim(),
        role: this.userEditRole,
        status: this.userEditStatus,
        preferred_language: this.userEditLang,
        response_preferences: this.userEditPrompt,
        quota_messages_per_day: this.userEditQuotaMessages ?? 0,
        quota_trackings_per_day: this.userEditQuotaTrackings ?? 0,
        quota_exports_per_day: this.userEditQuotaExports ?? 0,
      })
      .subscribe({
        next: (detail) => {
          this.userDetail.set(detail);
          this.userDetailSaving.set(false);
          this.userDetailSuccess.set(this.i18n.t('admin.userSaveSuccess'));
          this.refreshAll();
        },
        error: (err: HttpErrorResponse) => {
          this.userDetailSaving.set(false);
          this.userDetailError.set(
            typeof err.error?.detail === 'string' ? err.error.detail : this.i18n.t('admin.userSaveFailed'),
          );
        },
      });
  }

  validate(user: AdminUser): void {
    this.busyId.set(user.id);
    this.pendingError.set(null);
    this.pendingSuccess.set(null);
    this.admin.validateEmployee(user.id).subscribe({
      next: () => {
        this.busyId.set(null);
        this.pendingSuccess.set(this.i18n.t('admin.validateSuccess', { email: user.email }));
        this.refreshAll();
        this.loadPlatformNotifications();
      },
      error: (err: HttpErrorResponse) => {
        this.busyId.set(null);
        this.pendingError.set(
          typeof err.error?.detail === 'string' ? err.error.detail : this.i18n.t('admin.validateFailed'),
        );
      },
    });
  }

  reject(user: AdminUser): void {
    this.busyId.set(user.id);
    this.admin.rejectEmployee(user.id).subscribe({
      next: () => {
        this.busyId.set(null);
        this.pendingSuccess.set(this.i18n.t('admin.rejectSuccess', { email: user.email }));
        this.refreshAll();
        this.loadPlatformNotifications();
      },
      error: (err: HttpErrorResponse) => {
        this.busyId.set(null);
        this.pendingError.set(this.i18n.t('admin.rejectFailed'));
      },
    });
  }

  resetPasswordForDetail(): void {
    const detail = this.userDetail();
    if (!detail || detail.role !== 'employe') return;
    this.resetPassword({
      id: detail.id,
      email: detail.email,
      full_name: detail.full_name,
      role: detail.role,
      status: detail.status,
      organization_id: detail.organization_id,
      preferred_language: detail.preferred_language,
      created_at: detail.created_at,
    });
  }

  resetPassword(user: AdminUser): void {
    this.busyId.set(user.id);
    this.admin.resetEmployeePassword(user.id).subscribe({
      next: () => {
        this.busyId.set(null);
        this.pendingSuccess.set(this.i18n.t('admin.resetSuccess', { email: user.email }));
      },
      error: () => {
        this.busyId.set(null);
        this.pendingError.set(this.i18n.t('admin.resetFailed'));
      },
    });
  }

  roleLabel(role: string): string {
    const key = `admin.role.${role}`;
    const t = this.i18n.t(key);
    return t !== key ? t : role;
  }

  statusLabel(status: string): string {
    const key = `admin.status.${status}`;
    const t = this.i18n.t(key);
    return t !== key ? t : status;
  }

  logout(): void {
    this.auth.logout();
  }
}
