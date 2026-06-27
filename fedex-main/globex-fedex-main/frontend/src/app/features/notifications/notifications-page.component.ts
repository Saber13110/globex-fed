import { CommonModule } from '@angular/common';

import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';

import { Subscription } from 'rxjs';

import { FormsModule } from '@angular/forms';

import { ActivatedRoute, Router } from '@angular/router';

import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';



import { I18nService } from '../../core/i18n/i18n.service';

import { TranslatePipe } from '../../core/i18n/translate.pipe';

import { AuthService } from '../../core/services/auth.service';

import { ChatSessionSummary } from '../../core/services/chat-session.service';

import { ConversationSidebarBridgeService } from '../../core/services/conversation-sidebar-bridge.service';

import { SidebarSessionsService } from '../../core/services/sidebar-sessions.service';

import { SupportService, SupportTicketDetail, SupportTicketMessage } from '../../core/services/support.service';

import {

  UserNotification,

  UserNotificationsService,

} from '../../core/services/user-notifications.service';

import { UserPreferencesService } from '../../core/services/user-preferences.service';

import { Conversation } from '../chat/components/chat-item/chat-item.component';

import { SidebarComponent } from '../chat/components/sidebar/sidebar.component';

import { WorkspaceTopbarComponent } from '../chat/components/workspace-topbar/workspace-topbar.component';



type NotifSection = 'all' | 'unread' | 'support' | 'tracking' | 'documents' | 'security' | 'ai';



interface NotifGroup {

  key: string;

  labelKey: string;

  items: UserNotification[];

}



@Component({

  selector: 'app-notifications-page',

  standalone: true,

  imports: [CommonModule, FormsModule, TranslatePipe, SidebarComponent, WorkspaceTopbarComponent, MatSnackBarModule],

  templateUrl: './notifications-page.component.html',

  styleUrl: './notifications-page.component.scss',

})

export class NotificationsPageComponent implements OnInit, OnDestroy {

  notifications: UserNotification[] = [];

  statsItems: UserNotification[] = [];

  loading = false;

  error: string | null = null;

  search = '';

  activeSection: NotifSection = 'all';

  unreadCount = 0;

  total = 0;



  activeNotification: UserNotification | null = null;

  activeTicket: SupportTicketDetail | null = null;

  loadingTicket = false;

  replyMessage = '';

  submitting = false;

  uploadingAttachment = false;

  replyAttachmentUrl: string | null = null;

  replyAttachmentName = '';

  filterMenuOpen = false;



  sidebarCollapsed = false;

  sessions: ChatSessionSummary[] = [];

  loadingSessions = false;

  accountName = '';

  accountEmail = '';



  private readonly subs = new Subscription();

  private lastSyncedUnread = 0;

  private pendingNotifId: number | null = null;

  private pendingTicketId: number | null = null;



  readonly sections: { id: NotifSection; labelKey: string }[] = [

    { id: 'all', labelKey: 'notif.section.all' },

    { id: 'unread', labelKey: 'notif.section.unread' },

    { id: 'support', labelKey: 'notif.section.support' },

    { id: 'tracking', labelKey: 'notif.section.tracking' },

    { id: 'documents', labelKey: 'notif.section.documents' },

    { id: 'security', labelKey: 'notif.section.security' },

  ];



  constructor(

    private readonly notifApi: UserNotificationsService,

    private readonly support: SupportService,

    private readonly auth: AuthService,

    private readonly userPreferences: UserPreferencesService,

    private readonly i18n: I18nService,

    private readonly router: Router,

    private readonly route: ActivatedRoute,

    private readonly sidebarBridge: ConversationSidebarBridgeService,

    private readonly sidebarSessions: SidebarSessionsService,

    private readonly snack: MatSnackBar,

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



  get statSupport(): number {

    return this.statsItems.filter((n) => n.type === 'admin_reply' || n.type === 'support_message').length;

  }



  get statTracking(): number {

    return this.statsItems.filter((n) => n.type === 'tracking_update').length;

  }



  get statDocuments(): number {

    return this.statsItems.filter((n) => n.type === 'document_ready' || n.type === 'export_ready').length;

  }



  get statSecurity(): number {

    return this.statsItems.filter((n) => n.type === 'security_alert').length;

  }



  get groupedNotifications(): NotifGroup[] {

    const groups: NotifGroup[] = [];

    const buckets: Record<string, UserNotification[]> = {

      today: [],

      yesterday: [],

      older: [],

    };

    const now = new Date();

    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const startYesterday = new Date(startToday);

    startYesterday.setDate(startYesterday.getDate() - 1);



    for (const item of this.notifications) {

      const d = new Date(item.created_at);

      if (d >= startToday) buckets['today'].push(item);

      else if (d >= startYesterday) buckets['yesterday'].push(item);

      else buckets['older'].push(item);

    }



    if (buckets['today'].length) groups.push({ key: 'today', labelKey: 'notif.group.today', items: buckets['today'] });

    if (buckets['yesterday'].length) {

      groups.push({ key: 'yesterday', labelKey: 'notif.group.yesterday', items: buckets['yesterday'] });

    }

    if (buckets['older'].length) {

      groups.push({ key: 'older', labelKey: 'notif.group.older', items: buckets['older'] });

    }

    return groups;

  }



  ngOnInit(): void {

    const prefs = this.userPreferences.read();

    this.accountName = prefs.displayName || prefs.fullName;

    this.loadNotifications();

    this.sidebarSessions.ensureLoaded();

    this.subs.add(
      this.sidebarSessions.sessions$.subscribe((rows) => {
        this.sessions = rows;
      }),
    );

    this.subs.add(
      this.sidebarSessions.loading$.subscribe((loading) => {
        this.loadingSessions = loading;
      }),
    );

    if (this.auth.token()) {

      this.auth.me().subscribe({

        next: (profile) => {

          this.accountName = profile.full_name || this.accountName;

          this.accountEmail = profile.email;

          this.userPreferences.syncFromAuthProfile(profile);

          this.i18n.syncFromAuthProfile(profile.preferred_language);

        },

      });

    }

    this.route.queryParamMap.subscribe((params) => {

      const ticketId = Number(params.get('ticket'));

      const notifId = Number(params.get('notif'));

      this.pendingNotifId = Number.isFinite(notifId) && notifId > 0 ? notifId : null;

      this.pendingTicketId = Number.isFinite(ticketId) && ticketId > 0 ? ticketId : null;

      this.applyPendingSelection();

    });

    this.notifApi.startPolling(12_000);

    this.subs.add(
      this.notifApi.unread$.subscribe((count) => {
        const prev = this.lastSyncedUnread;
        this.unreadCount = count;
        this.lastSyncedUnread = count;
        if (count !== prev) {
          this.loadStats();
          if (count > prev) {
            this.loadNotifications();
          }
        }
      }),
    );

  }



  ngOnDestroy(): void {

    this.subs.unsubscribe();

    this.notifApi.stopPolling();

  }



  setSection(section: NotifSection): void {

    this.activeSection = section;

    this.filterMenuOpen = false;

    this.loadNotifications();

  }



  toggleFilterMenu(event: Event): void {

    event.stopPropagation();

    this.filterMenuOpen = !this.filterMenuOpen;

  }



  activeSectionLabel(): string {

    const sec = this.sections.find((s) => s.id === this.activeSection);

    return sec ? this.i18n.t(sec.labelKey) : this.i18n.t('notif.section.all');

  }



  @HostListener('document:click', ['$event'])
  closeFilterMenu(event: MouseEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.np-filter-wrap')) {
      return;
    }
    this.filterMenuOpen = false;
  }



  loadNotifications(): void {

    this.loading = true;

    this.error = null;

    const params: { status?: string; type?: string; q?: string; limit?: number } = { limit: 200 };

    if (this.activeSection === 'unread') params.status = 'unread';

    if (this.activeSection === 'support') params.type = 'support';

    if (this.activeSection === 'tracking') params.type = 'tracking_update';

    if (this.activeSection === 'documents') params.type = 'documents';

    if (this.activeSection === 'security') params.type = 'security_alert';

    if (this.activeSection === 'ai') params.type = 'ai_report';

    if (this.search.trim()) params.q = this.search.trim();



    this.notifApi.list(params).subscribe({

      next: (res) => {

        this.notifications = res.items;

        this.unreadCount = res.unread_count;

        this.lastSyncedUnread = res.unread_count;

        this.notifApi.setUnreadCount(res.unread_count);

        this.total = res.total;

        if (this.activeSection === 'all' || !this.statsItems.length) {
          this.statsItems = res.items;
        }

        this.loading = false;

        this.applyPendingSelection();

      },

      error: () => {

        this.loading = false;

        this.error = this.i18n.t('notif.loadError');

      },

    });

  }



  loadStats(): void {

    this.notifApi.list({ limit: 200 }).subscribe({

      next: (res) => {

        this.statsItems = res.items;

        this.unreadCount = res.unread_count;

        this.lastSyncedUnread = res.unread_count;

        this.notifApi.setUnreadCount(res.unread_count);

        this.total = res.total;

      },

    });

  }



  markAllRead(): void {

    this.notifApi.markAllRead().subscribe({

      next: () => {

        this.toast(this.i18n.t('notif.markAllSuccess'), 'success');

        this.notifApi.setUnreadCount(0);

        this.loadStats();

        this.loadNotifications();

      },

      error: () => this.toast(this.i18n.t('notif.markAllError'), 'error'),

    });

  }



  openDetails(item: UserNotification): void {

    this.activeNotification = item;

    this.activeTicket = null;

    if (!item.is_read) {

      this.notifApi.markRead(item.id).subscribe({

        next: () => {

          item.is_read = true;

          item.status = 'read';

          this.notifApi.setUnreadCount(Math.max(0, this.notifApi.unreadCount - 1));

        },

      });

    }

    if (item.related_ticket_id) {

      this.openTicketDrawer(item.related_ticket_id);

    }

  }



  closePanel(): void {

    this.activeNotification = null;

    this.activeTicket = null;

    this.replyMessage = '';

    this.clearReplyAttachment();

    void this.router.navigate([], {

      relativeTo: this.route,

      queryParams: { ticket: null, notif: null },

      queryParamsHandling: 'merge',

      replaceUrl: true,

    });

  }



  sendReply(): void {

    if (!this.activeTicket) return;

    const message = this.replyMessage.trim();

    if (!message && !this.replyAttachmentUrl) return;

    this.submitting = true;

    this.support.addMessage(this.activeTicket.id, message, this.replyAttachmentUrl).subscribe({

      next: (msg) => {

        this.submitting = false;

        this.replyMessage = '';

        this.clearReplyAttachment();

        this.activeTicket = {

          ...this.activeTicket!,

          messages: [...(this.activeTicket?.messages ?? []), msg],

        };

        this.toast(this.i18n.t('notif.replySent'), 'success');

      },

      error: () => {

        this.submitting = false;

        this.toast(this.i18n.t('notif.replyError'), 'error');

      },

    });

  }



  iconFor(type: string): string {

    const map: Record<string, string> = {

      support_message: 'message-square',

      admin_reply: 'message-square',

      tracking_update: 'package',

      document_ready: 'file-text',

      export_ready: 'file-text',

      system_alert: 'message-square',

      security_alert: 'shield-check',

      ai_report: 'sparkles',

    };

    return map[type] ?? 'message-square';

  }



  ticketLabel(item: UserNotification): string {

    if (item.related_ticket_id && this.activeTicket?.id === item.related_ticket_id && this.activeTicket.ticket_number) {

      return this.activeTicket.ticket_number;

    }

    return item.related_ticket_id ? `SUP-${item.related_ticket_id}` : '';

  }



  attachmentName(url: string): string {

    return this.support.attachmentDisplayName(url);

  }



  openAttachment(url: string, event: Event): void {

    event.preventDefault();

    event.stopPropagation();

    this.support.openAttachment(url).subscribe({

      error: () => this.toast(this.i18n.t('support.attachmentOpenError'), 'error'),

    });

  }



  onReplyAttachmentSelected(event: Event): void {

    const input = event.target as HTMLInputElement;

    const file = input.files?.[0];

    input.value = '';

    if (!file) {

      return;

    }

    const err = this.support.validateAttachmentFile(file);

    if (err === 'type') {

      this.toast(this.i18n.t('support.attachmentTypeError'), 'error');

      return;

    }

    if (err === 'size') {

      this.toast(this.i18n.t('support.attachmentSizeError'), 'error');

      return;

    }

    this.uploadingAttachment = true;

    this.support.uploadAttachment(file).subscribe({

      next: (res) => {

        this.uploadingAttachment = false;

        this.replyAttachmentUrl = res.url;

        this.replyAttachmentName = res.filename;

      },

      error: () => {

        this.uploadingAttachment = false;

        this.toast(this.i18n.t('support.attachmentUploadError'), 'error');

      },

    });

  }



  clearReplyAttachment(): void {

    this.replyAttachmentUrl = null;

    this.replyAttachmentName = '';

  }



  latestAdminMessage(): SupportTicketMessage | null {

    const messages = this.activeTicket?.messages ?? [];

    for (let i = messages.length - 1; i >= 0; i -= 1) {

      if (messages[i].author_role === 'admin') return messages[i];

    }

    return null;

  }



  adminInitial(msg: SupportTicketMessage): string {

    const name = (msg.author_name || 'A').trim();

    return name ? name.charAt(0).toUpperCase() : 'A';

  }



  accentClass(type: string): string {

    const map: Record<string, string> = {

      support_message: 'support',

      admin_reply: 'support',

      tracking_update: 'tracking',

      document_ready: 'document',

      export_ready: 'document',

      system_alert: 'system',

      security_alert: 'security',

      ai_report: 'ai',

    };

    return map[type] ?? 'system';

  }



  typeLabel(type: string): string {

    const map: Record<string, string> = {

      support_message: 'notif.type.support',

      admin_reply: 'notif.type.supportReply',

      tracking_update: 'notif.type.tracking',

      document_ready: 'notif.type.document',

      export_ready: 'notif.type.export',

      system_alert: 'notif.type.system',

      security_alert: 'notif.type.security',

      ai_report: 'notif.type.ai',

    };

    return this.i18n.t(map[type] ?? 'notif.type.system');

  }



  relativeTime(iso: string): string {

    const date = new Date(iso);

    const diff = Date.now() - date.getTime();

    const mins = Math.floor(diff / 60_000);

    if (mins < 1) return this.i18n.t('notif.time.justNow');

    if (mins < 60) return this.i18n.t('notif.time.minutes', { count: String(mins) });

    const hours = Math.floor(mins / 60);

    if (hours < 24) return this.i18n.t('notif.time.hours', { count: String(hours) });

    const days = Math.floor(hours / 24);

    if (days === 1) return this.i18n.t('notif.time.yesterday');

    if (days < 7) return this.i18n.t('notif.time.days', { count: String(days) });

    return this.formatDate(iso);

  }



  formatDate(iso: string): string {

    try {

      return new Intl.DateTimeFormat(this.i18n.langCode(), {

        dateStyle: 'medium',

        timeStyle: 'short',

      }).format(new Date(iso));

    } catch {

      return iso;

    }

  }



  toggleSidebar(): void {

    this.sidebarCollapsed = !this.sidebarCollapsed;

  }



  goToChat(sessionId?: string): void {
    this.sidebarBridge.openChat(sessionId);
  }

  newChat(): void {
    void this.router.navigateByUrl('/chat');
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



  openNotifications(): void {}



  openHelp(): void {

    void this.router.navigateByUrl('/help');

  }



  openProfile(): void {

    void this.router.navigateByUrl('/settings/profile');

  }



  openSettings(): void {

    void this.router.navigateByUrl('/settings/profile');

  }



  returnToAssistant(): void {

    void this.router.navigateByUrl('/chat');

  }



  logout(): void {

    this.auth.logout();

  }



  private applyPendingSelection(): void {

    if (this.pendingNotifId) {

      const found = this.notifications.find((n) => n.id === this.pendingNotifId);

      if (found) {

        this.openDetails(found);

        this.pendingNotifId = null;

        this.pendingTicketId = null;

        return;

      }

    }

    if (this.pendingTicketId) {

      const linked = this.notifications.find((n) => n.related_ticket_id === this.pendingTicketId);

      if (linked) {

        this.openDetails(linked);

      } else {

        this.openTicketDrawer(this.pendingTicketId);

      }

      this.pendingNotifId = null;

      this.pendingTicketId = null;

    }

  }



  private openTicketDrawer(ticketId: number): void {

    this.loadingTicket = true;

    this.support.getTicket(ticketId).subscribe({

      next: (ticket) => {

        this.activeTicket = ticket;

        this.loadingTicket = false;

      },

      error: () => {

        this.loadingTicket = false;

        this.toast(this.i18n.t('notif.ticketError'), 'error');

      },

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



  private toast(msg: string, type: 'success' | 'error'): void {

    this.snack.open(msg, this.i18n.t('common.close'), {

      duration: 4000,

      panelClass: type === 'success' ? 'set-snack--ok' : 'set-snack--err',

      horizontalPosition: 'end',

      verticalPosition: 'top',

    });

  }

}


