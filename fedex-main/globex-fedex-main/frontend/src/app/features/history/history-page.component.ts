import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { Subscription } from 'rxjs';

import { I18nService } from '../../core/i18n/i18n.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import { AuthService } from '../../core/services/auth.service';
import { ChatSessionService, ChatSessionSummary } from '../../core/services/chat-session.service';
import { ShipmentSummary } from '../../core/services/chatbot.service';
import { HistoryItem, HistoryService } from '../../core/services/history.service';
import { SupportService } from '../../core/services/support.service';
import { TrackingService, isSandboxWhitelistError, sandboxWhitelistMessage } from '../../core/services/tracking.service';
import { UserPreferencesService } from '../../core/services/user-preferences.service';
import { ConversationSidebarBridgeService } from '../../core/services/conversation-sidebar-bridge.service';
import { SidebarSessionsService } from '../../core/services/sidebar-sessions.service';
import { Conversation } from '../chat/components/chat-item/chat-item.component';
import { SidebarComponent, SidebarProject } from '../chat/components/sidebar/sidebar.component';
import { HistoryDetailDrawerComponent } from './components/history-detail-drawer/history-detail-drawer.component';

export type HistoryStatusFilter = 'all' | 'in_transit' | 'delivered' | 'exception' | 'ready' | 'archived';

export type HistoryStatusBadge = 'delivered' | 'in_transit' | 'exception' | 'ready';

@Component({
  selector: 'app-history-page',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe, SidebarComponent, HistoryDetailDrawerComponent],
  templateUrl: './history-page.component.html',
  styleUrl: './history-page.component.scss',
})
export class HistoryPageComponent implements OnInit, OnDestroy {
  items: HistoryItem[] = [];
  error: string | null = null;
  loading = false;

  searchQuery = '';
  statusFilter: HistoryStatusFilter = 'all';
  filtersOpen = false;
  sortNewest = true;

  page = 1;
  readonly pageSize = 10;

  drawerOpen = false;
  selectedItem: HistoryItem | null = null;
  drawerShipment: ShipmentSummary | null = null;
  drawerLoading = false;
  drawerError: string | null = null;
  highlightItemId: number | null = null;
  openCardMenuId: number | null = null;
  private pendingFocusTracking: string | null = null;

  sidebarCollapsed = false;
  search = '';
  sessions: ChatSessionSummary[] = [];
  loadingSessions = false;
  accountName = 'ana';
  accountEmail = '';
  userRole = '';
  unreadNotifications = 0;

  readonly statusFilters: HistoryStatusFilter[] = ['all', 'in_transit', 'delivered', 'exception', 'ready'];

  private readonly subs = new Subscription();

  constructor(
    private readonly history: HistoryService,
    private readonly tracking: TrackingService,
    private readonly auth: AuthService,
    private readonly chatSessions: ChatSessionService,
    private readonly support: SupportService,
    private readonly userPreferences: UserPreferencesService,
    private readonly i18n: I18nService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
    private readonly sidebarBridge: ConversationSidebarBridgeService,
    private readonly sidebarSessions: SidebarSessionsService,
  ) {}

  get accountLanguage(): string {
    return this.i18n.uiLanguageLabel();
  }

  get colorMode(): 'light' | 'dark' | 'auto' {
    return this.userPreferences.read().colorMode;
  }

  get accountAvatarInitial(): string {
    const value = (this.accountName || 'A').trim();
    return value ? value.charAt(0).toUpperCase() : 'A';
  }

  get accountAvatarClass(): string {
    const variant = this.userPreferences.read().avatarVariant % 6;
    return `sidebar__avatar--variant-${variant}`;
  }

  get pinnedConversations(): Conversation[] {
    return this.toConversations(this.sessions.filter((s) => s.is_pinned && !s.is_archived));
  }

  get recentConversations(): Conversation[] {
    return this.toConversations(this.sessions.filter((s) => !s.is_pinned && !s.is_archived));
  }

  get sidebarProjects(): SidebarProject[] {
    return [];
  }

  get filteredItems(): HistoryItem[] {
    const q = this.searchQuery.trim().toLowerCase();
    let rows = [...this.items];

    if (q) {
      rows = rows.filter((it) => {
        const blob = `${it.tracking_number} ${it.user_question} ${it.status ?? ''} ${it.current_location ?? ''}`.toLowerCase();
        return blob.includes(q);
      });
    }

    if (this.statusFilter !== 'all') {
      rows = rows.filter((it) => this.statusCategory(it) === this.statusFilter);
    }

    rows.sort((a, b) => {
      const da = new Date(a.created_at).getTime();
      const db = new Date(b.created_at).getTime();
      return this.sortNewest ? db - da : da - db;
    });

    return rows;
  }

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.filteredItems.length / this.pageSize));
  }

  get paginatedItems(): HistoryItem[] {
    const start = (this.page - 1) * this.pageSize;
    return this.filteredItems.slice(start, start + this.pageSize);
  }

  get pageNumbers(): number[] {
    const total = this.totalPages;
    const current = this.page;
    const window = 5;
    let start = Math.max(1, current - Math.floor(window / 2));
    const end = Math.min(total, start + window - 1);
    start = Math.max(1, end - window + 1);
    const pages: number[] = [];
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }

  get resultsFrom(): number {
    if (this.filteredItems.length === 0) {
      return 0;
    }
    return (this.page - 1) * this.pageSize + 1;
  }

  get resultsTo(): number {
    return Math.min(this.page * this.pageSize, this.filteredItems.length);
  }

  get requestCountLabel(): string {
    const count = this.filteredItems.length;
    return this.i18n.t('history.requestCount', { count: String(count) });
  }

  ngOnInit(): void {
    const prefs = this.userPreferences.read();
    this.accountName = prefs.displayName || prefs.fullName;
    this.refresh();
    this.sidebarSessions.ensureLoaded();
    this.subs.add(this.sidebarSessions.sessions$.subscribe((rows) => (this.sessions = rows)));
    this.subs.add(this.sidebarSessions.loading$.subscribe((loading) => (this.loadingSessions = loading)));
    this.loadUnread();
    if (this.auth.token()) {
      this.auth.me().subscribe({
        next: (profile) => {
          this.accountName = profile.full_name || this.accountName;
          this.accountEmail = profile.email;
          this.userRole = profile.role;
          this.userPreferences.syncFromAuthProfile(profile);
          this.i18n.syncFromAuthProfile(profile.preferred_language);
        },
      });
    }
    this.route.queryParamMap.subscribe((params) => {
      this.pendingFocusTracking = params.get('tracking')?.trim() || null;
      if (!this.loading && this.items.length) {
        this.applyTrackingFocus();
      }
    });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.drawerOpen) {
      this.closeDrawer();
    }
    if (this.filtersOpen) {
      this.filtersOpen = false;
    }
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.filtersOpen = false;
    this.openCardMenuId = null;
  }

  toggleCardMenu(event: Event, id: number): void {
    event.stopPropagation();
    this.openCardMenuId = this.openCardMenuId === id ? null : id;
  }

  openCardDiscussion(event: Event, item: HistoryItem): void {
    event.stopPropagation();
    this.openCardMenuId = null;
    if (!item.session_id) {
      return;
    }
    void this.router.navigate(['/chat'], { queryParams: { session: item.session_id } });
  }

  openDetailsFromMenu(event: Event, item: HistoryItem): void {
    event.stopPropagation();
    this.openCardMenuId = null;
    this.openDetails(item);
  }

  copyTrackingNumber(event: Event, trackingNumber: string): void {
    event.stopPropagation();
    this.openCardMenuId = null;
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(trackingNumber);
    }
  }

  startTracking(): void {
    void this.router.navigateByUrl('/chat');
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.history.list(200).subscribe({
      next: (rows) => {
        this.items = rows;
        this.loading = false;
        this.clampPage();
        this.applyTrackingFocus();
      },
      error: (err) => {
        this.loading = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : this.i18n.t('history.loadError');
      },
    });
  }

  export(): void {
    const lang = this.i18n.toBackendCode() as 'fr' | 'en' | 'ar';
    this.history
      .downloadExcel({
        limit: 200,
        lang,
        columns: [
          'tracking_number',
          'status',
          'current_location',
          'estimated_delivery',
          'user_question',
          'created_at',
        ],
        includeEvents: true,
      })
      .subscribe({
        error: () => {
          this.error = this.i18n.t('history.exportError');
        },
      });
  }

  onSearchChange(): void {
    this.page = 1;
    this.clampPage();
  }

  setStatusFilter(filter: HistoryStatusFilter): void {
    this.statusFilter = filter;
    this.page = 1;
    this.clampPage();
  }

  toggleFilters(): void {
    this.filtersOpen = !this.filtersOpen;
  }

  setSort(newest: boolean): void {
    this.sortNewest = newest;
    this.filtersOpen = false;
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages) {
      return;
    }
    this.page = page;
  }

  openDetails(item: HistoryItem): void {
    this.selectedItem = item;
    this.drawerOpen = true;
    this.drawerShipment = null;
    this.drawerError = null;
    this.drawerLoading = true;
    this.highlightItemId = item.id;

    this.tracking.getTracking(item.tracking_number).subscribe({
      next: (res) => {
        this.drawerShipment = {
          tracking_number: res.tracking_number,
          status: res.status,
          status_code: res.status_code,
          status_description: res.status_description,
          current_location: res.current_location,
          city: res.city,
          state_or_province: res.state_or_province,
          country: res.country,
          estimated_delivery: res.estimated_delivery,
          actual_delivery: res.actual_delivery,
          events: res.events ?? [],
          visibility_events: res.visibility_events,
          service_type: res.service_type,
          service_description: res.service_description,
          shipper: res.shipper,
          recipient: res.recipient,
          origin_location: res.origin_location,
          destination_location: res.destination_location,
          weight: res.weight,
          dimensions: res.dimensions,
          package_type: res.package_type,
          package_count: res.package_count,
          special_handlings: res.special_handlings,
          received_by_name: res.received_by_name,
          service_commit_message: res.service_commit_message,
          pod_available: res.pod_available,
          pod_info: res.pod_info,
          source: res.source,
          sandbox_whitelist_denied: false,
        };
        this.drawerLoading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.drawerLoading = false;
        if (isSandboxWhitelistError(err)) {
          this.drawerShipment = {
            tracking_number: item.tracking_number,
            status: null,
            current_location: null,
            estimated_delivery: null,
            sandbox_whitelist_denied: true,
          };
          this.drawerError = sandboxWhitelistMessage(err) || this.i18n.t('tracking.sandboxDeniedMessage');
        } else {
          this.drawerError = this.i18n.t('history.timelineError');
        }
      },
    });
  }

  closeDrawer(): void {
    this.drawerOpen = false;
    this.selectedItem = null;
    this.drawerShipment = null;
    this.drawerError = null;
    this.highlightItemId = null;
  }

  openDiscussionFromDrawer(): void {
    const item = this.selectedItem;
    if (!item?.session_id) {
      return;
    }
    this.closeDrawer();
    void this.router.navigate(['/chat'], { queryParams: { session: item.session_id } });
  }

  statusBadge(item: HistoryItem): HistoryStatusBadge {
    const category = this.statusCategory(item);
    if (category === 'delivered') return 'delivered';
    if (category === 'exception') return 'exception';
    if (category === 'ready') return 'ready';
    return 'in_transit';
  }

  statusBadgeLabel(item: HistoryItem): string {
    const badge = this.statusBadge(item);
    const keys: Record<HistoryStatusBadge, string> = {
      delivered: 'history.badgeDelivered',
      in_transit: 'history.badgeInTransit',
      exception: 'history.badgeException',
      ready: 'history.badgeReady',
    };
    return this.i18n.t(keys[badge]);
  }

  filterLabel(filter: HistoryStatusFilter): string {
    const keys: Record<HistoryStatusFilter, string> = {
      all: 'history.filterAll',
      in_transit: 'history.filterInTransit',
      delivered: 'history.filterDelivered',
      exception: 'history.filterException',
      ready: 'history.filterReady',
      archived: 'history.filterArchived',
    };
    return this.i18n.t(keys[filter]);
  }

  isExportItem(item: HistoryItem): boolean {
    const blob = `${item.user_question} ${item.bot_response}`.toLowerCase();
    return /export|excel|xlsx|rapport|report/.test(blob);
  }

  formatActivityShort(iso: string): string {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return iso;
    }
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((startToday.getTime() - startDate.getTime()) / 86_400_000);
    const locale = this.i18n.langCode() === 'en' ? 'en-US' : this.i18n.langCode() === 'ar' ? 'ar' : 'fr-FR';
    const time = date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 0) {
      return `${this.i18n.t('history.today')} · ${time}`;
    }
    if (diffDays === 1) {
      return `${this.i18n.t('sidebar.group.yesterday')} · ${time}`;
    }
    const day = date.toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' });
    return `${day} · ${time}`;
  }

  formatActivityDate(iso: string): string {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return iso;
    }
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((startToday.getTime() - startDate.getTime()) / 86_400_000);
    const locale = this.i18n.langCode() === 'en' ? 'en-US' : this.i18n.langCode() === 'ar' ? 'ar' : 'fr-FR';
    const time = date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 0) {
      return `${this.i18n.t('history.today')}, ${time}`;
    }
    if (diffDays === 1) {
      return `${this.i18n.t('sidebar.group.yesterday')}, ${time}`;
    }
    return date.toLocaleString(locale, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  toggleSidebar(): void {
    this.sidebarCollapsed = !this.sidebarCollapsed;
  }

  toggleTheme(): void {
    const prefs = this.userPreferences.read();
    const next = prefs.colorMode === 'dark' ? 'light' : 'dark';
    this.userPreferences.write({ ...prefs, colorMode: next });
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  goToChat(sessionId?: string): void {
    this.sidebarBridge.openChat(sessionId);
  }

  onSidebarRenameConversation(id: string): void {
    this.sidebarBridge.navigateAction(id, 'rename');
  }

  onSidebarTogglePinConversation(id: string): void {
    this.sidebarBridge.togglePin(this.sessions, id, () => this.sidebarSessions.refresh());
  }

  onSidebarMoveConversation(id: string): void {
    this.sidebarBridge.navigateAction(id, 'move');
  }

  onSidebarDeleteConversation(id: string): void {
    this.sidebarBridge.navigateAction(id, 'delete');
  }

  goToHistory(): void {
    void this.router.navigateByUrl('/history');
  }

  goToDocuments(): void {
    void this.router.navigateByUrl('/documents');
  }

  openSupport(): void {
    void this.router.navigateByUrl('/help?support=1');
  }

  openHelp(): void {
    void this.router.navigateByUrl('/help');
  }

  openProfile(): void {
    void this.router.navigateByUrl('/settings/profile');
  }

  openSettings(): void {
    void this.router.navigateByUrl('/settings/profile');
  }

  logout(): void {
    this.auth.logout();
  }

  private statusCategory(item: HistoryItem): HistoryStatusFilter {
    const status = (item.status ?? '').toLowerCase();
    if (/deliver|livré|livre/.test(status)) {
      return 'delivered';
    }
    if (/exception|delay|retard|hold|problem|incident|failed|échec/.test(status)) {
      return 'exception';
    }
    if (/ready for pickup|pickup|disponible|prêt/.test(status)) {
      return 'ready';
    }
    if (/transit|vehicle|depart|arriv|ship|en route|course/.test(status)) {
      return 'in_transit';
    }
    return 'in_transit';
  }

  private applyTrackingFocus(): void {
    const tracking = this.pendingFocusTracking;
    if (!tracking) {
      return;
    }
    const normalized = tracking.replace(/\s/g, '');
    const match = this.items.find(
      (it) => it.tracking_number === tracking || it.tracking_number.replace(/\s/g, '') === normalized,
    );
    if (!match) {
      return;
    }
    this.searchQuery = tracking;
    this.page = 1;
    setTimeout(() => {
      this.openDetails(match);
      document.getElementById(`history-item-${match.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
  }

  private clampPage(): void {
    if (this.page > this.totalPages) {
      this.page = this.totalPages;
    }
    if (this.page < 1) {
      this.page = 1;
    }
  }

  private loadUnread(): void {
    this.support.getUnreadCount().subscribe({
      next: ({ count }) => {
        this.unreadNotifications = count ?? 0;
      },
      error: () => {},
    });
  }

  private toConversations(rows: ChatSessionSummary[]): Conversation[] {
    return rows.map((s) => ({
      id: String(s.id),
      title: s.title,
      updatedAt: s.updated_at,
      isPinned: s.is_pinned,
    }));
  }
}
