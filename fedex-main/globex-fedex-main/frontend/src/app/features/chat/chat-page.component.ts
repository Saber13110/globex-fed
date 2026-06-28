import { CommonModule } from '@angular/common';
import { AfterViewChecked, Component, HostListener, OnDestroy, OnInit } from '@angular/core';
import { finalize, Subscription } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import {
  ChatCollection,
  ChatSessionMessage,
  ChatSessionService,
  ChatSessionSummary,
} from '../../core/services/chat-session.service';
import { ChatSendPayload, AgentSuggestion } from '../../core/models/chat-send.model';
import { ChatbotService } from '../../core/services/chatbot.service';
import { HistoryService } from '../../core/services/history.service';
import { SupportService } from '../../core/services/support.service';
import { UserNotificationsService } from '../../core/services/user-notifications.service';
import { SidebarSessionsService } from '../../core/services/sidebar-sessions.service';
import { unpackMessageText } from '../../core/utils/message-attachment.util';
import { UserPreferencesService } from '../../core/services/user-preferences.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import { ChatInputComponent } from './components/chat-input/chat-input.component';
import { ChatHeroComponent, HeroAction, HeroStat } from './components/chat-hero/chat-hero.component';
import { ConversationThreadComponent } from './components/conversation/conversation-thread.component';
import { Conversation } from './components/chat-item/chat-item.component';
import { UiMessage } from './components/message-list/message-list.component';
import { ShareConversationComponent } from './components/share-conversation/share-conversation.component';
import {
  SidebarComponent,
  SidebarFolderShortcut,
  SidebarProject,
  SidebarRecentGroup,
} from './components/sidebar/sidebar.component';
import { WorkspaceTopbarComponent } from './components/workspace-topbar/workspace-topbar.component';

interface SearchResultGroup {
  label: string;
  sessions: ChatSessionSummary[];
}

interface FolderShortcutDef {
  id: string;
  labelKey: string;
  keys: string[];
  defaultName: string;
}

@Component({
  selector: 'app-chat-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ChatInputComponent,
    SidebarComponent,
    ShareConversationComponent,
    ChatHeroComponent,
    ConversationThreadComponent,
    WorkspaceTopbarComponent,
    TranslatePipe,
  ],
  templateUrl: './chat-page.component.html',
  styleUrl: './chat-page.component.scss',
})
export class ChatPageComponent implements OnInit, AfterViewChecked, OnDestroy {
  messages: UiMessage[] = [];
  sessions: ChatSessionSummary[] = [];
  collections: ChatCollection[] = [];
  loadingSessions = false;
  loadingMessages = false;
  isBotThinking = false;
  search = '';
  smartView = 'all';
  selectedCollectionId: number | null = null;
  includeArchived = false;
  renamingSessionId: number | null = null;
  renameDraft = '';
  sidebarCollapsed = false;
  sessionMenuOpenId: number | null = null;
  accountMenuOpen = false;
  currentView: 'chat' | 'discussions' | 'search' | 'project' = 'chat';
  projectTab: 'chats' | 'sources' = 'chats';
  discussionsQuery = '';
  searchOverlayQuery = '';
  searchModalOpen = false;
  accountName = '';
  accountEmail = '';
  userRole = '';
  portalMode: 'client' | 'employee' = 'client';
  unreadNotifications = 0;
  accountAvatarUrl: string | null = null;
  /** Instructions IA définies par l'admin en base (prioritaires sur le local). */
  serverUserPrompt = '';
  collectionModalOpen = false;
  tagsModalOpen = false;
  newFolderModalOpen = false;
  modalSession: ChatSessionSummary | null = null;
  collectionDraft = '';
  tagsDraft = '';
  newFolderDraft = '';
  shareModalOpen = false;
  shareModalLoading = false;
  shareIncludeTrackingDetails = false;
  shareLink = '';
  renameModalOpen = false;
  deleteModalOpen = false;
  movingModalOpen = false;
  moveDraft = '';
  renameModalDraft = '';
  targetSessionForModal: ChatSessionSummary | null = null;
  actionFeedback: string | null = null;

  private nextId = 2;
  private shouldScroll = false;
  private feedbackTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly subs = new Subscription();

  sessionId: number | null = null;
  error: string | null = null;

  private pendingSessionId: number | null = null;
  private pendingSessionAction: 'rename' | 'move' | 'delete' | null = null;

  private readonly folderShortcutDefs: FolderShortcutDef[] = [
    { id: 'personal', labelKey: 'sidebar.folder.personal', keys: ['personnel', 'personal', 'perso'], defaultName: 'Personal' },
    {
      id: 'professional',
      labelKey: 'sidebar.folder.professional',
      keys: ['professionnel', 'professional', 'pro'],
      defaultName: 'Professional',
    },
    { id: 'exports', labelKey: 'sidebar.folder.exports', keys: ['export', 'exportation'], defaultName: 'Exports' },
    { id: 'archives', labelKey: 'sidebar.folder.archives', keys: ['archive', 'archives'], defaultName: 'Archives' },
  ];

  constructor(
    private readonly chatbot: ChatbotService,
    private readonly chatSessions: ChatSessionService,
    private readonly history: HistoryService,
    private readonly support: SupportService,
    private readonly userNotifications: UserNotificationsService,
    readonly auth: AuthService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
    private readonly userPreferences: UserPreferencesService,
    private readonly i18n: I18nService,
    private readonly sidebarSessions: SidebarSessionsService,
  ) {}

  get heroActions(): HeroAction[] {
    const ids = ['track', 'excel', 'proof', 'issue'] as const;
    const icons: Record<(typeof ids)[number], HeroAction['icon']> = {
      track: 'track',
      excel: 'excel',
      proof: 'proof',
      issue: 'issue',
    };
    return ids.map((id) => ({
      id,
      title: this.i18n.t(`chat.hero.action.${id}.title`),
      subtitle: this.i18n.t(`chat.hero.action.${id}.subtitle`),
      text: this.i18n.t(`chat.hero.action.${id}.text`),
      icon: icons[id],
    }));
  }

  get heroStats(): HeroStat[] {
    const active = this.sessions.filter((s) => !s.is_archived);
    const docs = active.filter((s) => /export|excel|pdf|rapport|report|preuve|proof|document/i.test(s.title));
    return [
      {
        id: 'parcels',
        value: String(active.length),
        label: this.i18n.t('chat.hero.stat.parcels'),
        tone: 'purple',
        icon: 'box',
      },
      {
        id: 'documents',
        value: String(docs.length),
        label: this.i18n.t('chat.hero.stat.documents'),
        tone: 'green',
        icon: 'doc',
      },
      {
        id: 'api',
        value: this.i18n.t('chat.hero.stat.apiName'),
        label: this.i18n.t('chat.hero.stat.operational'),
        tone: 'orange',
        icon: 'shield',
        operational: true,
      },
    ];
  }

  get sidebarFolderShortcuts(): SidebarFolderShortcut[] {
    return this.folderShortcutDefs.map((d) => ({
      id: d.id,
      labelKey: d.labelKey,
      count: this.countFolderMatches(d.keys),
    }));
  }

  get moveFolderChoices(): { id: string; label: string; collectionId: number | null }[] {
    return this.folderShortcutDefs.map((d) => ({
      id: d.id,
      label: this.i18n.t(d.labelKey),
      collectionId: this.findCollectionForShortcut(d.id)?.id ?? null,
    }));
  }

  get customCollectionsForMove(): ChatCollection[] {
    return this.collections.filter((c) => !this.folderShortcutDefs.some((d) => this.collectionMatchesShortcut(c, d.id)));
  }

  get sidebarRecentGroups(): SidebarRecentGroup[] {
    const rows = [...this.sessions]
      .filter((s) => !s.is_archived)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    const pinned = this.toConversations(rows.filter((s) => s.is_pinned));
    const recent = this.toConversations(rows.filter((s) => !s.is_pinned));
    const all = [...pinned, ...recent].slice(0, 14);
    const groups: SidebarRecentGroup[] = [];
    let currentLabel = '';
    let bucket: Conversation[] = [];
    for (const conv of all) {
      const label = this.relativeConversationGroupLabel(conv.updatedAt);
      if (label !== currentLabel) {
        if (bucket.length) {
          groups.push({ label: currentLabel, conversations: bucket });
        }
        currentLabel = label;
        bucket = [conv];
      } else {
        bucket.push(conv);
      }
    }
    if (bucket.length) {
      groups.push({ label: currentLabel, conversations: bucket });
    }
    const weekLabel = this.i18n.t('sidebar.group.thisWeek');
    const allowed = new Set([
      this.i18n.t('sidebar.group.today'),
      this.i18n.t('sidebar.group.yesterday'),
      weekLabel,
    ]);
    return groups.filter((g) => allowed.has(g.label));
  }

  get heroDisplayName(): string {
    const name = (this.accountName || '').trim();
    if (!name) {
      return '';
    }
    const parts = name.split(/\s+/);
    if (parts.length === 1) {
      return parts[0];
    }
    return parts.slice(0, 2).join(' ');
  }

  get accountFirstName(): string {
    const name = (this.accountName || '').trim();
    if (!name) {
      return '';
    }
    return name.split(/\s+/)[0];
  }

  get showHero(): boolean {
    return this.currentView === 'chat' && this.sessionId === null && this.messages.length === 0;
  }

  get filteredDiscussions(): ChatSessionSummary[] {
    const q = this.discussionsQuery.trim().toLowerCase();
    if (!q) {
      return this.sessions;
    }
    return this.sessions.filter((s) => s.title.toLowerCase().includes(q));
  }

  get groupedSearchResults(): SearchResultGroup[] {
    const rows = [...this.filteredSearchResults]
      .filter((s) => !s.is_archived)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

    const groups: SearchResultGroup[] = [];
    let currentLabel = '';
    let currentSessions: ChatSessionSummary[] = [];

    for (const session of rows) {
      const label = this.formatSearchGroupLabel(session.updated_at);
      if (label !== currentLabel) {
        if (currentSessions.length > 0) {
          groups.push({ label: currentLabel, sessions: currentSessions });
        }
        currentLabel = label;
        currentSessions = [session];
      } else {
        currentSessions.push(session);
      }
    }
    if (currentSessions.length > 0) {
      groups.push({ label: currentLabel, sessions: currentSessions });
    }
    return groups;
  }

  get filteredSearchResults(): ChatSessionSummary[] {
    const q = this.searchOverlayQuery.trim().toLowerCase();
    if (!q) {
      return this.sessions;
    }
    return this.sessions.filter((s) => s.title.toLowerCase().includes(q));
  }

  get projectSessions(): ChatSessionSummary[] {
    if (this.selectedCollectionId === null) {
      return [];
    }
    return this.sessions.filter((s) => s.collection_id === this.selectedCollectionId);
  }

  get pinnedConversations(): Conversation[] {
    return this.toConversations(this.sessions.filter((s) => s.is_pinned && !s.is_archived));
  }

  get recentConversations(): Conversation[] {
    return this.toConversations(this.sessions.filter((s) => !s.is_pinned && !s.is_archived));
  }

  get sidebarProjects(): SidebarProject[] {
    return this.collections.map((project) => ({
      id: project.id,
      name: project.name,
      count: this.sessions.filter((s) => s.collection_id === project.id).length,
      isActive: this.selectedCollectionId === project.id,
    }));
  }

  get activeSession(): ChatSessionSummary | null {
    return this.resolveSessionForActions();
  }

  get activeSessionFolderName(): string | null {
    const folderId = this.activeSession?.collection_id;
    if (!folderId) {
      return null;
    }
    return this.collections.find((c) => c.id === folderId)?.name ?? null;
  }

  get greetingPrefix(): string {
    return this.i18n.greetingPrefix();
  }

  get totalChatsCount(): number {
    return this.sessions.filter((s) => !s.is_archived).length;
  }

  get colorMode(): 'light' | 'dark' | 'auto' {
    return this.userPreferences.read().colorMode;
  }

  get languageShort(): string {
    return this.i18n.languageShort();
  }

  get accountAvatarInitial(): string {
    const value = (this.accountName || 'A').trim();
    return value ? value.charAt(0).toUpperCase() : 'A';
  }

  get accountAvatarClass(): string {
    const prefs = this.userPreferences.read();
    const variant = prefs.avatarVariant % 6;
    return `sidebar__avatar--variant-${variant}`;
  }

  get selectedCollectionName(): string | null {
    if (this.selectedCollectionId === null) {
      return null;
    }
    const row = this.collections.find((c) => c.id === this.selectedCollectionId);
    return row?.name ?? null;
  }

  ngAfterViewChecked(): void {
    if (!this.shouldScroll) {
      return;
    }
    const root = document.querySelector('.chat-scroll');
    if (root) {
      root.scrollTop = root.scrollHeight;
    }
    this.shouldScroll = false;
  }

  get accountLanguage(): string {
    return this.i18n.uiLanguageLabel();
  }

  ngOnInit(): void {
    const prefs = this.userPreferences.read();
    this.accountName = prefs.displayName || prefs.fullName;
    this.resetMessages();
    this.loadCollections();
    const sessionRaw = this.route.snapshot.queryParamMap.get('session');
    if (sessionRaw) {
      const id = Number(sessionRaw);
      if (Number.isFinite(id) && id > 0) {
        this.pendingSessionId = id;
      }
    }
    const actionRaw = this.route.snapshot.queryParamMap.get('action');
    if (actionRaw === 'rename' || actionRaw === 'move' || actionRaw === 'delete') {
      this.pendingSessionAction = actionRaw;
    }
    this.loadSessions();
    if (this.auth.token()) {
      this.auth.me().subscribe({
        next: (profile) => {
          this.accountName = profile.full_name || this.accountName;
          this.accountEmail = profile.email;
          this.userRole = profile.role;
          const pic = (profile as { profile_picture_url?: string | null }).profile_picture_url;
          this.accountAvatarUrl = pic && String(pic).trim() ? String(pic) : null;
          this.userPreferences.syncFromAuthProfile(profile);
          this.auth.getMyPreferences().subscribe({
            next: (prefs) => {
              this.serverUserPrompt = (prefs.active || '').trim();
            },
            error: () => {
              this.serverUserPrompt = (profile.response_preferences || '').trim();
            },
          });
          this.i18n.syncFromAuthProfile(profile.preferred_language);
          const uiLang = this.i18n.toBackendCode();
          if (profile.preferred_language !== uiLang) {
            this.auth.updateProfile({ preferred_language: uiLang }).subscribe({ error: () => undefined });
          }
        },
        error: () => {
          this.auth.clearLocalSession();
          void this.router.navigateByUrl('/login');
        },
      });
      this.subs.add(
        this.userNotifications.unread$.subscribe((count) => {
          this.unreadNotifications = count;
        }),
      );
      this.userNotifications.startPolling(12_000);
    }
    const sharedToken = this.route.snapshot.paramMap.get('token');
    if (sharedToken) {
      this.importSharedConversationFromToken(sharedToken);
    }
  }

  newConversation(): void {
    this.currentView = this.selectedCollectionId ? 'project' : 'chat';
    this.sessionId = null;
    this.error = null;
    this.resetMessages();
  }

  home(): void {
    this.selectedCollectionId = null;
    this.newConversation();
  }

  toggleSidebar(): void {
    this.sidebarCollapsed = !this.sidebarCollapsed;
  }

  toggleSessionMenu(sessionId: number): void {
    this.sessionMenuOpenId = this.sessionMenuOpenId === sessionId ? null : sessionId;
  }

  openDiscussionsView(): void {
    this.currentView = 'discussions';
    this.sessionMenuOpenId = null;
  }

  openSearchView(): void {
    this.searchModalOpen = true;
    this.searchOverlayQuery = '';
    this.sessionMenuOpenId = null;
  }

  closeSearchView(): void {
    this.searchModalOpen = false;
    this.searchOverlayQuery = '';
  }

  @HostListener('document:keydown', ['$event'])
  onGlobalKeydown(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (this.searchModalOpen) {
        this.closeSearchView();
      } else {
        this.openSearchView();
      }
    }
    if (event.key === 'Escape' && this.searchModalOpen) {
      this.closeSearchView();
    }
  }

  openAccountMenu(): void {
    this.accountMenuOpen = !this.accountMenuOpen;
  }

  openSettings(): void {
    this.accountMenuOpen = false;
    void this.router.navigateByUrl('/settings/profile');
  }

  openHistory(): void {
    void this.router.navigateByUrl('/history');
  }

  openHelp(): void {
    void this.router.navigateByUrl('/help');
  }

  toggleTheme(): void {
    const prefs = this.userPreferences.read();
    const next = prefs.colorMode === 'dark' ? 'light' : 'dark';
    this.userPreferences.write({ ...prefs, colorMode: next });
  }

  onHeroAction(action: HeroAction): void {
    if (action.id === 'excel') {
      this.sendPreset('Exporte mon historique de tracking en Excel');
      return;
    }
    if (action.id === 'issue') {
      void this.router.navigateByUrl('/help');
      return;
    }
    this.sendPreset(action.text);
  }

  openSession(session: ChatSessionSummary): void {
    this.closeSearchView();
    this.error = null;
    this.loadingMessages = true;
    this.currentView = 'chat';
    this.sessionId = session.id;
    this.chatSessions.listMessages(session.id).subscribe({
      next: (rows) => {
        this.messages = this.mapRowsToUi(rows);
        this.nextId = this.messages.reduce((max, m) => Math.max(max, m.id), 0) + 1;
        this.shouldScroll = true;
        this.loadingMessages = false;
        this.ensureSessionRecord(session.id, session.title);
        this.applyPendingSessionAction();
      },
      error: (err) => {
        this.loadingMessages = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : 'Impossible de charger la conversation.';
      },
    });
  }

  openSessionById(id: number): void {
    this.closeSearchView();
    const existing = this.sessions.find((s) => s.id === id);
    if (existing) {
      this.openSession(existing);
      return;
    }
    this.error = null;
    this.loadingMessages = true;
    this.currentView = 'chat';
    this.sessionId = id;
    this.chatSessions.listMessages(id).subscribe({
      next: (rows) => {
        this.messages = this.mapRowsToUi(rows);
        this.nextId = this.messages.reduce((max, m) => Math.max(max, m.id), 0) + 1;
        this.shouldScroll = true;
        this.loadingMessages = false;
        this.ensureSessionRecord(id);
        this.applyPendingSessionAction();
      },
      error: (err) => {
        this.loadingMessages = false;
        this.sessionId = null;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : 'Impossible de charger la conversation.';
      },
    });
  }

  onSidebarSearchQueryChange(value: string): void {
    this.search = value;
  }

  onSidebarSelectConversation(id: string): void {
    const session = this.findSessionById(id);
    if (!session) {
      return;
    }
    this.openSession(session);
  }

  onHeaderRenameConversation(): void {
    const session = this.resolveSessionForActions();
    if (session) {
      this.openRenameModal(session);
    }
  }

  onHeaderMoveConversation(): void {
    const session = this.resolveSessionForActions();
    if (session) {
      this.openMoveModal(session);
    }
  }

  onHeaderDeleteConversation(): void {
    const session = this.resolveSessionForActions();
    if (session) {
      this.openDeleteModal(session);
    }
  }

  onHeaderTogglePin(): void {
    const session = this.resolveSessionForActions();
    if (session) {
      this.togglePin(session);
    }
  }

  onSidebarRenameConversationRequest(id: string): void {
    const session = this.findSessionById(id);
    if (session) {
      this.openRenameModal(session);
      return;
    }
    const asNumber = Number(id);
    if (Number.isFinite(asNumber) && asNumber > 0) {
      this.openSessionById(asNumber);
      this.pendingSessionAction = 'rename';
    }
  }

  onSidebarRenameConversation(payload: { id: string; title: string }): void {
    const session = this.findSessionById(payload.id);
    if (!session) {
      return;
    }
    this.chatSessions.update(session.id, { title: payload.title }).subscribe({
      next: () => {
        this.loadSessions();
        this.showActionFeedback('Conversation renommée');
      },
      error: () => {
        this.error = 'Impossible de renommer la conversation.';
      },
    });
  }

  onSidebarTogglePinConversation(id: string): void {
    const session = this.findSessionById(id);
    if (session) {
      this.togglePin(session);
      return;
    }
    const asNumber = Number(id);
    if (!Number.isFinite(asNumber) || asNumber <= 0) {
      return;
    }
    this.chatSessions.list({ limit: 150 }).subscribe({
      next: (rows) => {
        this.sessions = rows;
        const found = rows.find((row) => row.id === asNumber);
        if (found) {
          this.togglePin(found);
        }
      },
    });
  }

  onSidebarDeleteConversation(id: string): void {
    const session = this.findSessionById(id);
    if (session) {
      this.openDeleteModal(session);
      return;
    }
    const asNumber = Number(id);
    if (Number.isFinite(asNumber) && asNumber > 0) {
      this.pendingSessionAction = 'delete';
      this.openSessionById(asNumber);
    }
  }

  onSidebarMoveConversation(id: string): void {
    const session = this.findSessionById(id);
    if (session) {
      this.openMoveModal(session);
      return;
    }
    const asNumber = Number(id);
    if (Number.isFinite(asNumber) && asNumber > 0) {
      this.pendingSessionAction = 'move';
      this.openSessionById(asNumber);
    }
  }

  startRename(session: ChatSessionSummary): void {
    this.renamingSessionId = session.id;
    this.renameDraft = session.title;
  }

  cancelRename(): void {
    this.renamingSessionId = null;
    this.renameDraft = '';
  }

  saveRename(session: ChatSessionSummary): void {
    const title = this.renameDraft.trim();
    if (!title) {
      this.error = 'Le titre ne peut pas être vide.';
      return;
    }
    this.chatSessions.update(session.id, { title }).subscribe({
      next: () => {
        this.cancelRename();
        this.loadSessions();
      },
      error: () => {
        this.error = 'Impossible de renommer la conversation.';
      },
    });
  }

  togglePin(session: ChatSessionSummary): void {
    const nextPinned = !session.is_pinned;
    this.chatSessions.update(session.id, { is_pinned: nextPinned }).subscribe({
      next: (updated) => {
        const index = this.sessions.findIndex((row) => row.id === session.id);
        if (index >= 0) {
          this.sessions = [
            ...this.sessions.slice(0, index),
            updated,
            ...this.sessions.slice(index + 1),
          ];
        } else {
          this.loadSessions();
        }
        this.showActionFeedback(nextPinned ? 'Conversation épinglée' : 'Conversation désépinglée');
      },
      error: () => {
        this.error = "Impossible de modifier l'épingle.";
      },
    });
  }

  addToFavorites(session: ChatSessionSummary): void {
    this.togglePin(session);
  }

  addToProject(session: ChatSessionSummary): void {
    this.openCollectionModal(session);
  }

  renameSession(session: ChatSessionSummary): void {
    this.startRename(session);
  }

  archiveSession(session: ChatSessionSummary): void {
    this.chatSessions.update(session.id, { is_archived: !session.is_archived }).subscribe({
      next: () => this.loadSessions(),
      error: () => {
        this.error = 'Impossible de modifier l’archivage.';
      },
    });
  }

  deleteSession(session: ChatSessionSummary): void {
    this.chatSessions.delete(session.id).subscribe({
      next: () => {
        if (this.sessionId === session.id) {
          this.newConversation();
        }
        this.loadSessions();
        this.showActionFeedback('Conversation supprimée');
      },
      error: () => {
        this.error = 'Suppression impossible.';
      },
    });
  }

  assignCollection(session: ChatSessionSummary): void {
    this.chatSessions.update(session.id, { collection_id: 0 }).subscribe({
      next: () => {
        this.loadSessions();
      },
      error: () => {
        this.error = 'Affectation au dossier impossible.';
      },
    });
  }

  editTags(session: ChatSessionSummary): void {
    this.openTagsModal(session);
  }

  saveTags(): void {
    if (!this.modalSession) {
      return;
    }
    this.chatSessions.update(this.modalSession.id, { tags: this.tagsDraft.trim() }).subscribe({
      next: () => this.loadSessions(),
      error: () => {
        this.error = 'Mise à jour des tags impossible.';
      },
    });
    this.closeAllModals();
  }

  createCollection(): void {
    this.openNewFolderModal();
  }

  selectCollection(collectionId: number | null): void {
    this.selectedCollectionId = collectionId;
    this.currentView = collectionId === null ? 'chat' : 'project';
    this.projectTab = 'chats';
    this.sessionId = null;
    this.resetMessages();
    this.loadSessions();
  }

  isCollectionSelected(collectionId: number | null): boolean {
    return this.selectedCollectionId === collectionId;
  }

  collectionChatCount(collectionId: number): number {
    return this.sessions.filter((s) => s.collection_id === collectionId).length;
  }

  saveNewCollection(): void {
    const cleaned = this.newFolderDraft.trim();
    if (!cleaned) return;
    this.chatSessions.createCollection(cleaned).subscribe({
      next: () => {
        this.loadCollections();
        this.closeAllModals();
        this.showActionFeedback('Dossier créé');
      },
      error: () => {
        this.error = 'Création du dossier impossible.';
      },
    });
  }

  applyFilters(): void {
    this.loadSessions();
  }

  clearFilters(): void {
    this.search = '';
    this.smartView = 'all';
    this.selectedCollectionId = null;
    this.includeArchived = false;
    this.loadSessions();
  }

  onAgentSuggestionActivate(suggestion: AgentSuggestion): void {
    this.onSend({
      text: suggestion.prefill,
    });
  }

  onAgentAnswers(event: { flowId: string; answers: Record<string, string> }): void {
    this.onSend({
      text: '',
      agentFlowId: event.flowId,
      agentAnswers: event.answers,
    });
  }

  sendPreset(text: string): void {
    this.onSend({ text });
  }

  onSend(payload: ChatSendPayload | string): void {
    const normalized: ChatSendPayload = typeof payload === 'string' ? { text: payload } : payload;
    const text = normalized.text?.trim() ?? '';
    const image = normalized.image;

    if (!text && !image && !normalized.agentAnswers) {
      return;
    }

    const isDoc = Boolean(image && !image.mimeType.startsWith('image/'));

    this.error = null;
    this.currentView = 'chat';
    const wasNewConversation = this.sessionId === null;
    const targetCollectionId = this.selectedCollectionId;
    this.messages = [
      ...this.messages,
      {
        id: this.nextId++,
        role: 'user',
        text:
          text ||
          (image
            ? this.i18n.t(isDoc ? 'chat.input.documentSent' : 'chat.input.imageSent')
            : normalized.agentAnswers
              ? this.i18n.t('chat.agent.answersSent')
              : ''),
        imageUrl: image?.previewUrl,
        fileName: image?.name,
        isDocument: isDoc,
        source: 'user_input',
      },
    ];
    this.shouldScroll = true;
    this.isBotThinking = true;

    const prefs = this.userPreferences.read();
    const responsePrefs = this.serverUserPrompt || prefs.responsePreferences || '';
    this.chatbot
      .sendMessage(text, this.sessionId, {
        response_preferences: responsePrefs,
        preferred_name: prefs.displayName || prefs.fullName || '',
        ui_language: this.i18n.toBackendCode(),
        image,
        agent_mode: Boolean(normalized.agentFlowId),
        agent_flow_id: normalized.agentFlowId,
        agent_answers: normalized.agentAnswers,
      })
      .pipe(finalize(() => {
        this.isBotThinking = false;
      }))
      .subscribe({
      next: (res) => {
        this.sessionId = res.session_id;
        this.upsertSession(this.buildSessionStub(res.session_id, res.session_title || undefined));
        if (res.session_title) {
          this.applySessionTitle(res.session_id, res.session_title);
        }
        if (wasNewConversation && typeof targetCollectionId === 'number' && targetCollectionId > 0) {
          this.chatSessions.update(res.session_id, { collection_id: targetCollectionId }).subscribe({
            next: () => this.loadSessions(),
            error: () => {
              this.error = 'Impossible d’affecter la nouvelle conversation au dossier sélectionné.';
            },
          });
        }
        this.messages = [
          ...this.messages,
          {
            id: this.nextId++,
            role: 'bot',
            text: res.reply,
            source: res.source,
            shipment: res.shipment ?? undefined,
            trackingNumber: res.tracking_number ?? undefined,
            agentQuestionnaire: res.agent_questionnaire ?? undefined,
            agentPhase: res.agent_phase,
            agentSuggestion: res.agent_suggestion ?? undefined,
            exportDownload: res.export_download ?? undefined,
          },
        ];
        this.notifyResponseCompletion(res.reply);
        this.shouldScroll = true;
        this.loadSessions();
      },
      error: (err) => {
        const detail = err?.error?.detail;
        const msg = typeof detail === 'string' ? detail : 'Impossible d’envoyer le message.';
        const isSecurity =
          err?.status === 400 &&
          typeof detail === 'string' &&
          (detail.toLowerCase().includes('sécurité') ||
            detail.toLowerCase().includes('security') ||
            detail.toLowerCase().includes('prompt injection'));
        this.error = isSecurity ? null : msg;
        if (isSecurity) {
          this.messages = [
            ...this.messages,
            {
              id: this.nextId++,
              role: 'bot',
              text: msg,
              source: 'security',
            },
          ];
          this.shouldScroll = true;
        }
      },
      });
  }

  private notifyResponseCompletion(reply: string): void {
    const prefs = this.userPreferences.read();
    if (!prefs.responseCompletionNotifications || typeof Notification === 'undefined') {
      return;
    }
    const show = () => {
      const body = reply.length > 120 ? `${reply.slice(0, 117)}...` : reply;
      new Notification('Réponse terminée', { body });
    };
    if (Notification.permission === 'granted') {
      show();
      return;
    }
    if (Notification.permission === 'default') {
      void Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          show();
        }
      });
    }
  }

  logout(): void {
    this.auth.logout();
  }

  openShareModal(): void {
    if (!this.activeSession) {
      return;
    }
    this.shareModalOpen = true;
    this.shareIncludeTrackingDetails = false;
    this.generateShareLink();
  }

  openRenameModal(session: ChatSessionSummary): void {
    this.closeActionModals();
    this.targetSessionForModal = session;
    this.renameModalDraft = session.title;
    this.renameModalOpen = true;
  }

  saveRenameModal(): void {
    if (!this.targetSessionForModal) {
      return;
    }
    const cleaned = this.renameModalDraft.trim();
    if (!cleaned) {
      return;
    }
    this.chatSessions.update(this.targetSessionForModal.id, { title: cleaned }).subscribe({
      next: () => {
        this.loadSessions();
        this.showActionFeedback('Conversation renommée');
      },
      error: () => {
        this.error = 'Impossible de renommer la conversation.';
      },
    });
    this.closeActionModals();
  }

  openDeleteModal(session: ChatSessionSummary): void {
    this.closeActionModals();
    this.targetSessionForModal = session;
    this.deleteModalOpen = true;
  }

  confirmDeleteModal(): void {
    if (!this.targetSessionForModal) {
      return;
    }
    this.deleteSession(this.targetSessionForModal);
    this.closeActionModals();
  }

  openMoveModal(session: ChatSessionSummary): void {
    this.closeActionModals();
    this.targetSessionForModal = session;
    this.moveDraft = session.collection_id ? String(session.collection_id) : '';
    this.loadCollections();
    this.movingModalOpen = true;
  }

  saveMoveModal(): void {
    if (!this.targetSessionForModal) {
      return;
    }
    const cleaned = this.moveDraft.trim();
    const collection_id = cleaned ? Number(cleaned) : 0;
    if (cleaned && (!Number.isFinite(collection_id) || collection_id <= 0)) {
      this.error = 'Dossier invalide.';
      return;
    }
    this.chatSessions.update(this.targetSessionForModal.id, { collection_id }).subscribe({
      next: () => {
        this.loadSessions();
        this.showActionFeedback('Conversation déplacée');
      },
      error: () => {
        this.error = 'Déplacement vers le dossier impossible.';
      },
    });
    this.closeActionModals();
  }

  moveToFolderFromModal(collectionId: number): void {
    if (!this.targetSessionForModal || !Number.isFinite(collectionId) || collectionId <= 0) {
      this.error = 'Dossier invalide.';
      return;
    }
    this.assignSessionToCollection(collectionId);
  }

  moveConversationToShortcut(shortcutId: string): void {
    if (!this.targetSessionForModal) {
      return;
    }
    const def = this.folderShortcutDefs.find((d) => d.id === shortcutId);
    if (!def) {
      return;
    }
    const existing = this.findCollectionForShortcut(shortcutId);
    if (existing) {
      this.assignSessionToCollection(existing.id);
      return;
    }
    this.chatSessions.createCollection(def.defaultName).subscribe({
      next: (created) => {
        this.collections = [...this.collections, created];
        this.assignSessionToCollection(created.id);
      },
      error: () => {
        this.error = 'Déplacement vers le dossier impossible.';
      },
    });
  }

  isSessionInFolderShortcut(shortcutId: string): boolean {
    const session = this.targetSessionForModal;
    const collection = this.findCollectionForShortcut(shortcutId);
    if (!session?.collection_id || !collection) {
      return false;
    }
    return session.collection_id === collection.id;
  }

  isSessionInCollection(collectionId: number): boolean {
    return this.targetSessionForModal?.collection_id === collectionId;
  }

  private assignSessionToCollection(collectionId: number): void {
    if (!this.targetSessionForModal) {
      return;
    }
    this.chatSessions.update(this.targetSessionForModal.id, { collection_id: collectionId }).subscribe({
      next: () => {
        this.loadSessions();
        this.closeActionModals();
        this.showActionFeedback('Conversation déplacée');
      },
      error: () => {
        this.error = 'Déplacement vers le dossier impossible.';
      },
    });
  }

  private findCollectionForShortcut(shortcutId: string): ChatCollection | undefined {
    return this.collections.find((c) => this.collectionMatchesShortcut(c, shortcutId));
  }

  private collectionMatchesShortcut(collection: ChatCollection, shortcutId: string): boolean {
    const n = collection.name.toLowerCase();
    const def = this.folderShortcutDefs.find((d) => d.id === shortcutId);
    if (!def) {
      return false;
    }
    return def.keys.some((k) => n.includes(k));
  }

  togglePinActiveSession(): void {
    this.onHeaderTogglePin();
  }

  closeActionModals(): void {
    this.renameModalOpen = false;
    this.deleteModalOpen = false;
    this.movingModalOpen = false;
    this.targetSessionForModal = null;
    this.renameModalDraft = '';
    this.moveDraft = '';
  }

  onShareIncludeTrackingDetailsChange(value: boolean): void {
    this.shareIncludeTrackingDetails = value;
  }

  generateShareLink(): void {
    if (!this.activeSession) {
      return;
    }
    this.shareModalLoading = true;
    this.chatSessions.createShareLink(this.activeSession.id, this.shareIncludeTrackingDetails).subscribe({
      next: (res) => {
        this.shareLink = `${window.location.origin}/chat/shared/${res.share_token}`;
        this.shareModalLoading = false;
        this.showActionFeedback('Lien de partage prêt');
      },
      error: () => {
        this.shareModalLoading = false;
        this.error = 'Impossible de générer le lien de partage.';
      },
    });
  }

  private importSharedConversationFromToken(token: string): void {
    this.chatSessions.importSharedConversation(token).subscribe({
      next: (res) => {
        void this.router.navigateByUrl('/chat');
        this.currentView = 'chat';
        this.sessionId = res.session_id;
        this.loadSessions();
        this.chatSessions.listMessages(res.session_id).subscribe({
          next: (rows) => {
            this.messages = this.mapRowsToUi(rows);
            this.shouldScroll = true;
          },
        });
      },
      error: () => {
        this.error = 'Lien partagé invalide ou expiré.';
      },
    });
  }

  private applySessionTitle(sessionId: number, title: string): void {
    const cleaned = title.trim();
    if (!cleaned) {
      return;
    }
    this.sessions = this.sessions.map((s) => (s.id === sessionId ? { ...s, title: cleaned } : s));
  }

  private resetMessages(): void {
    this.messages = [];
    this.nextId = 1;
  }

  private loadSessions(): void {
    this.loadingSessions = true;
    this.chatSessions
      .list({
        limit: 150,
        search: this.search || undefined,
        smart_view: this.smartView,
        collection_id: this.selectedCollectionId ?? undefined,
        include_archived: this.includeArchived,
      })
      .subscribe({
        next: (rows) => {
          this.sessions = rows;
          this.loadingSessions = false;
          if (this.isSidebarSessionList()) {
            this.sidebarSessions.publish(rows);
          }
          this.flushPendingSessionOpen();
        },
        error: () => {
          this.sessions = [];
          this.loadingSessions = false;
          this.flushPendingSessionOpen();
        },
      });
  }

  private isSidebarSessionList(): boolean {
    return !this.search && !this.smartView && this.selectedCollectionId === null && !this.includeArchived;
  }

  openProfile(): void {
    void this.router.navigateByUrl('/settings/profile');
  }

  openDocuments(): void {
    void this.router.navigateByUrl('/documents');
  }

  openSupport(): void {
    void this.router.navigateByUrl('/help?support=1');
  }

  onFolderShortcut(id: string): void {
    const match = this.findCollectionForShortcut(id);
    if (match) {
      this.selectCollection(match.id);
      return;
    }
    this.actionFeedback = this.i18n.t('sidebar.folderEmpty');
    setTimeout(() => {
      this.actionFeedback = '';
    }, 2800);
  }

  openNotificationsPanel(): void {
    void this.router.navigateByUrl('/notifications');
  }

  private countFolderMatches(keys: string[]): number {
    if (keys.some((k) => k.includes('archive'))) {
      return this.sessions.filter((s) => s.is_archived).length;
    }
    return this.collections
      .filter((c) => keys.some((k) => c.name.toLowerCase().includes(k)))
      .reduce((sum, c) => sum + this.sessions.filter((s) => s.collection_id === c.id && !s.is_archived).length, 0);
  }

  private relativeConversationGroupLabel(isoDate: string): string {
    const date = new Date(isoDate);
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.floor((startToday.getTime() - day.getTime()) / 86400000);
    if (diffDays === 0) {
      return this.i18n.t('sidebar.group.today');
    }
    if (diffDays === 1) {
      return this.i18n.t('sidebar.group.yesterday');
    }
    if (diffDays < 7) {
      return this.i18n.t('sidebar.group.thisWeek');
    }
    if (date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear()) {
      return this.i18n.t('sidebar.group.thisMonth');
    }
    return this.formatSearchGroupLabel(isoDate);
  }

  private formatSearchGroupLabel(isoDate: string): string {
    const date = new Date(isoDate);
    const now = new Date();
    if (date.getFullYear() < now.getFullYear()) {
      return String(date.getFullYear());
    }
    const locale =
      this.i18n.langCode() === 'en' ? 'en-US' : this.i18n.langCode() === 'ar' ? 'ar' : 'fr-FR';
    const month = new Intl.DateTimeFormat(locale, { month: 'long' }).format(date);
    return month.charAt(0).toUpperCase() + month.slice(1);
  }

  private flushPendingSessionOpen(): void {
    if (this.pendingSessionId === null) {
      this.applyPendingSessionAction();
      return;
    }
    const id = this.pendingSessionId;
    this.pendingSessionId = null;
    this.openSessionById(id);
  }

  private applyPendingSessionAction(): void {
    if (!this.pendingSessionAction || !this.sessionId) {
      return;
    }
    const session = this.resolveSessionForActions();
    if (!session) {
      return;
    }
    const action = this.pendingSessionAction;
    this.pendingSessionAction = null;
    void this.router.navigate([], {
      queryParams: { action: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
    if (action === 'rename') {
      this.openRenameModal(session);
    } else if (action === 'move') {
      this.openMoveModal(session);
    } else if (action === 'delete') {
      this.openDeleteModal(session);
    }
  }

  private resolveSessionForActions(): ChatSessionSummary | null {
    if (!this.sessionId) {
      return null;
    }
    return this.sessions.find((s) => s.id === this.sessionId) ?? this.buildSessionStub(this.sessionId);
  }

  private ensureSessionRecord(sessionId: number, title?: string): void {
    if (!this.sessions.some((s) => s.id === sessionId)) {
      this.upsertSession(this.buildSessionStub(sessionId, title));
    }
  }

  private buildSessionStub(id: number, title?: string): ChatSessionSummary {
    return {
      id,
      title: title?.trim() || this.i18n.t('conversation.newTitle'),
      collection_id: null,
      tags: '',
      is_pinned: false,
      is_archived: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
  }

  private upsertSession(session: ChatSessionSummary): void {
    const index = this.sessions.findIndex((row) => row.id === session.id);
    if (index >= 0) {
      this.sessions = [
        ...this.sessions.slice(0, index),
        { ...this.sessions[index], ...session },
        ...this.sessions.slice(index + 1),
      ];
      return;
    }
    this.sessions = [session, ...this.sessions];
  }

  private findSessionById(id: string): ChatSessionSummary | undefined {
    const asNumber = Number(id);
    if (!Number.isFinite(asNumber)) {
      return undefined;
    }
    return this.sessions.find((s) => s.id === asNumber);
  }

  private filteredBySidebarSearch(rows: ChatSessionSummary[]): ChatSessionSummary[] {
    const q = this.search.trim().toLowerCase();
    if (!q) {
      return rows;
    }
    return rows.filter((row) => row.title.toLowerCase().includes(q));
  }

  private toConversations(rows: ChatSessionSummary[]): Conversation[] {
    return rows.map((row) => ({
      id: String(row.id),
      title: row.title,
      updatedAt: row.updated_at,
      isPinned: row.is_pinned,
      isActive: this.sessionId === row.id && this.currentView === 'chat',
    }));
  }

  private loadCollections(): void {
    this.chatSessions.listCollections().subscribe({
      next: (rows) => {
        this.collections = rows;
      },
      error: () => {
        this.collections = [];
      },
    });
  }

  private mapRowsToUi(rows: ChatSessionMessage[]): UiMessage[] {
    return rows
      .filter((r): r is ChatSessionMessage & { sender: 'user' | 'bot' } => r.sender === 'user' || r.sender === 'bot')
      .map((r) => {
        const unpacked = unpackMessageText(r.message_text);
        return {
          id: r.id,
          role: r.sender,
          text: unpacked.text,
          imageUrl: unpacked.imageUrl,
          fileName: unpacked.fileName,
          isDocument: unpacked.isDocument,
          source: (r as { source?: UiMessage['source'] }).source ?? 'unknown',
        };
      });
  }

  openCollectionModal(session: ChatSessionSummary): void {
    this.closeAllModals();
    this.modalSession = session;
    this.collectionDraft = session.collection_id ? String(session.collection_id) : '';
    this.collectionModalOpen = true;
  }

  saveCollectionAssignment(): void {
    if (!this.modalSession) {
      return;
    }
    const cleaned = this.collectionDraft.trim();
    const collection_id = cleaned ? Number(cleaned) : 0;
    if (cleaned && !Number.isFinite(collection_id)) {
      this.error = 'ID dossier invalide.';
      return;
    }
    this.chatSessions.update(this.modalSession.id, { collection_id }).subscribe({
      next: () => this.loadSessions(),
      error: () => {
        this.error = 'Affectation au dossier impossible.';
      },
    });
    this.closeAllModals();
  }

  pickCollection(id: number): void {
    this.collectionDraft = `${id}`;
  }

  openTagsModal(session: ChatSessionSummary): void {
    this.closeAllModals();
    this.modalSession = session;
    this.tagsDraft = session.tags ?? '';
    this.tagsModalOpen = true;
  }

  openNewFolderModal(): void {
    this.closeAllModals();
    this.newFolderDraft = '';
    this.newFolderModalOpen = true;
  }

  closeAllModals(): void {
    this.collectionModalOpen = false;
    this.tagsModalOpen = false;
    this.newFolderModalOpen = false;
    this.modalSession = null;
    this.collectionDraft = '';
    this.tagsDraft = '';
    this.newFolderDraft = '';
  }

  private showActionFeedback(message: string): void {
    this.actionFeedback = message;
    if (this.feedbackTimer) {
      clearTimeout(this.feedbackTimer);
    }
    this.feedbackTimer = setTimeout(() => {
      this.actionFeedback = null;
      this.feedbackTimer = null;
    }, 1800);
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.userNotifications.stopPolling();
  }
}
