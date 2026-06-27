import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { I18nService } from '../../core/i18n/i18n.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import { AuthService } from '../../core/services/auth.service';
import { ChatSessionService, ChatSessionSummary } from '../../core/services/chat-session.service';
import {
  SupportService,
  SupportTicketDetail,
  SupportTicketRead,
} from '../../core/services/support.service';
import { UserPreferencesService } from '../../core/services/user-preferences.service';
import { ConversationSidebarBridgeService } from '../../core/services/conversation-sidebar-bridge.service';
import { SidebarSessionsService } from '../../core/services/sidebar-sessions.service';
import { Conversation } from '../chat/components/chat-item/chat-item.component';
import { SidebarComponent } from '../chat/components/sidebar/sidebar.component';

@Component({
  selector: 'app-support-page',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe, SidebarComponent],
  templateUrl: './support-page.component.html',
  styleUrl: './support-page.component.scss',
})
export class SupportPageComponent implements OnInit, OnDestroy {
  tickets: SupportTicketRead[] = [];
  activeTicket: SupportTicketDetail | null = null;
  loadingTickets = false;
  loadingThread = false;
  error: string | null = null;

  showNewForm = false;
  newSubject = '';
  newMessage = '';
  replyMessage = '';
  submitting = false;
  uploadingAttachment = false;
  newAttachmentUrl: string | null = null;
  newAttachmentName = '';
  replyAttachmentUrl: string | null = null;
  replyAttachmentName = '';

  sidebarCollapsed = false;
  search = '';
  sessions: ChatSessionSummary[] = [];
  loadingSessions = false;
  accountName = '';
  accountEmail = '';
  unreadNotifications = 0;

  private readonly subs = new Subscription();

  constructor(
    private readonly support: SupportService,
    private readonly chatSessions: ChatSessionService,
    private readonly auth: AuthService,
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

  ngOnInit(): void {
    const prefs = this.userPreferences.read();
    this.accountName = prefs.displayName || prefs.fullName;
    this.loadTickets();
    this.sidebarSessions.ensureLoaded();
    this.subs.add(this.sidebarSessions.sessions$.subscribe((rows) => (this.sessions = rows)));
    this.subs.add(this.sidebarSessions.loading$.subscribe((loading) => (this.loadingSessions = loading)));
    this.loadUnread();
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
      if (Number.isFinite(ticketId) && ticketId > 0) {
        this.openTicket(ticketId);
      }
    });
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  loadTickets(): void {
    this.loadingTickets = true;
    this.support.listTickets().subscribe({
      next: (res) => {
        this.tickets = res.items;
        this.loadingTickets = false;
        if (!this.activeTicket && this.tickets.length > 0 && !this.showNewForm) {
          const fromQuery = Number(this.route.snapshot.queryParamMap.get('ticket'));
          if (Number.isFinite(fromQuery) && fromQuery > 0) {
            this.openTicket(fromQuery);
          }
        }
      },
      error: () => {
        this.loadingTickets = false;
        this.error = this.i18n.t('support.loadError');
      },
    });
  }

  openTicket(id: number): void {
    this.showNewForm = false;
    this.loadingThread = true;
    this.error = null;
    this.support.getTicket(id).subscribe({
      next: (ticket) => {
        this.activeTicket = ticket;
        this.loadingThread = false;
        void this.router.navigate([], {
          relativeTo: this.route,
          queryParams: { ticket: id },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      },
      error: () => {
        this.loadingThread = false;
        this.error = this.i18n.t('support.threadError');
      },
    });
  }

  startNewTicket(): void {
    this.activeTicket = null;
    this.showNewForm = true;
    this.newSubject = '';
    this.newMessage = '';
    this.clearNewAttachment();
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { ticket: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  submitNewTicket(): void {
    const subject = this.newSubject.trim();
    const message = this.newMessage.trim();
    if (subject.length < 3 || message.length < 10) {
      this.error = this.i18n.t('support.formInvalid');
      return;
    }
    this.submitting = true;
    this.error = null;
    this.support.createTicket({ subject, message, attachmentUrl: this.newAttachmentUrl }).subscribe({
      next: (created) => {
        this.submitting = false;
        this.showNewForm = false;
        this.clearNewAttachment();
        this.openTicket(created.id);
        this.loadTickets();
      },
      error: () => {
        this.submitting = false;
        this.error = this.i18n.t('support.submitError');
      },
    });
  }

  sendReply(): void {
    if (!this.activeTicket) {
      return;
    }
    const message = this.replyMessage.trim();
    if (!message && !this.replyAttachmentUrl) {
      return;
    }
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
      },
      error: () => {
        this.submitting = false;
        this.error = this.i18n.t('support.replyError');
      },
    });
  }

  statusLabel(status: string): string {
    return status === 'closed' ? this.i18n.t('support.statusClosed') : this.i18n.t('support.statusOpen');
  }

  onNewAttachmentSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    this.uploadAttachmentFile(file, 'new');
  }

  onReplyAttachmentSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    this.uploadAttachmentFile(file, 'reply');
  }

  clearNewAttachment(): void {
    this.newAttachmentUrl = null;
    this.newAttachmentName = '';
  }

  clearReplyAttachment(): void {
    this.replyAttachmentUrl = null;
    this.replyAttachmentName = '';
  }

  attachmentName(url: string): string {
    return this.support.attachmentDisplayName(url);
  }

  openAttachment(url: string, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    this.support.openAttachment(url).subscribe({
      error: () => {
        this.error = this.i18n.t('support.attachmentOpenError');
      },
    });
  }

  private uploadAttachmentFile(file: File, target: 'new' | 'reply'): void {
    const err = this.support.validateAttachmentFile(file);
    if (err === 'type') {
      this.error = this.i18n.t('support.attachmentTypeError');
      return;
    }
    if (err === 'size') {
      this.error = this.i18n.t('support.attachmentSizeError');
      return;
    }
    this.uploadingAttachment = true;
    this.error = null;
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.uploadingAttachment = false;
        if (target === 'new') {
          this.newAttachmentUrl = res.url;
          this.newAttachmentName = res.filename;
        } else {
          this.replyAttachmentUrl = res.url;
          this.replyAttachmentName = res.filename;
        }
      },
      error: () => {
        this.uploadingAttachment = false;
        this.error = this.i18n.t('support.attachmentUploadError');
      },
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
