import { CommonModule } from '@angular/common';

import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';

import { FormsModule } from '@angular/forms';

import { Router } from '@angular/router';

import { Subscription } from 'rxjs';



import { I18nService } from '../../core/i18n/i18n.service';

import { TranslatePipe } from '../../core/i18n/translate.pipe';

import { AuthService } from '../../core/services/auth.service';

import { ChatSessionService, ChatSessionSummary } from '../../core/services/chat-session.service';

import { ConversationSidebarBridgeService } from '../../core/services/conversation-sidebar-bridge.service';

import { SidebarSessionsService } from '../../core/services/sidebar-sessions.service';

import { HistoryItem, HistoryService } from '../../core/services/history.service';

import { SupportService } from '../../core/services/support.service';

import { UserPreferencesService } from '../../core/services/user-preferences.service';

import { Conversation } from '../chat/components/chat-item/chat-item.component';

import { SidebarComponent } from '../chat/components/sidebar/sidebar.component';

import {
  buildDocumentDownloadSpec,
  classifyDocumentBlob,
} from '../../core/utils/document-catalog.util';



export interface UserDocumentItem {

  id: string;

  title: string;

  type: 'export' | 'proof' | 'tracking' | 'report';

  trackingNumber?: string;

  createdAt: string;

  sessionId?: number;

  historyId?: number;

  fileSizeKb?: number;

  sourceText?: string;

}



export type DocumentTypeFilter = 'all' | 'export' | 'proof' | 'report';



@Component({

  selector: 'app-documents-page',

  standalone: true,

  imports: [CommonModule, FormsModule, TranslatePipe, SidebarComponent],

  templateUrl: './documents-page.component.html',

  styleUrl: './documents-page.component.scss',

})

export class DocumentsPageComponent implements OnInit, OnDestroy {

  documents: UserDocumentItem[] = [];

  loading = false;

  downloading = false;

  error: string | null = null;



  searchQuery = '';

  typeFilter: DocumentTypeFilter = 'all';

  sortRecent = true;



  openMenuDocId: string | null = null;

  renameModalOpen = false;

  deleteModalOpen = false;

  renameDraft = '';

  targetDoc: UserDocumentItem | null = null;



  private hiddenDocIds = new Set<string>();

  private titleOverrides = new Map<string, string>();



  sidebarCollapsed = false;

  search = '';

  sessions: ChatSessionSummary[] = [];

  loadingSessions = false;

  accountName = '';

  accountEmail = '';

  unreadNotifications = 0;

  private readonly subs = new Subscription();

  constructor(

    private readonly history: HistoryService,

    private readonly chatSessions: ChatSessionService,

    private readonly support: SupportService,

    private readonly auth: AuthService,

    private readonly userPreferences: UserPreferencesService,

    private readonly i18n: I18nService,

    private readonly router: Router,

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



  get visibleDocuments(): UserDocumentItem[] {

    let rows = this.documents.filter((doc) => !this.hiddenDocIds.has(doc.id));

    rows = rows.map((doc) => ({

      ...doc,

      title: this.titleOverrides.get(doc.id) ?? doc.title,

    }));



    const q = this.searchQuery.trim().toLowerCase();

    if (q) {

      rows = rows.filter((doc) => {

        const blob = `${doc.title} ${doc.trackingNumber ?? ''} ${this.typeLabel(doc.type)}`.toLowerCase();

        return blob.includes(q);

      });

    }



    if (this.typeFilter !== 'all') {

      rows = rows.filter((doc) => doc.type === this.typeFilter || (this.typeFilter === 'report' && doc.type === 'tracking'));

    }



    rows.sort((a, b) => {

      const da = new Date(a.createdAt).getTime();

      const db = new Date(b.createdAt).getTime();

      return this.sortRecent ? db - da : da - db;

    });



    return rows;

  }



  get statTotal(): number {

    return this.documents.filter((d) => !this.hiddenDocIds.has(d.id)).length;

  }



  get statProofs(): number {

    return this.documents.filter((d) => !this.hiddenDocIds.has(d.id) && d.type === 'proof').length;

  }



  get statExports(): number {

    return this.documents.filter((d) => !this.hiddenDocIds.has(d.id) && d.type === 'export').length;

  }



  ngOnInit(): void {

    const prefs = this.userPreferences.read();

    this.accountName = prefs.displayName || prefs.fullName;

    this.loadDocuments();

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

  }



  @HostListener('document:click')

  closeMenusOnOutsideClick(): void {

    this.openMenuDocId = null;

  }



  loadDocuments(): void {

    this.loading = true;

    this.error = null;

    this.history.list(100).subscribe({

      next: (rows) => {

        this.documents = this.buildDocuments(rows);

        this.loading = false;

      },

      error: () => {

        this.loading = false;

        this.error = this.i18n.t('documents.loadError');

      },

    });

  }



  typeLabel(type: UserDocumentItem['type']): string {

    const keys: Record<UserDocumentItem['type'], string> = {

      export: 'documents.typeExport',

      proof: 'documents.typeProof',

      tracking: 'documents.typeTracking',

      report: 'documents.typeReport',

    };

    return this.i18n.t(keys[type]);

  }



  statusLabel(doc: UserDocumentItem): string {

    return doc.type === 'export' ? this.i18n.t('documents.statusGenerated') : this.i18n.t('documents.statusReady');

  }



  fileSizeLabel(doc: UserDocumentItem): string {

    if (doc.fileSizeKb) {

      return doc.fileSizeKb >= 1024 ? `${(doc.fileSizeKb / 1024).toFixed(1)} MB` : `${doc.fileSizeKb} KB`;

    }

    return '—';

  }



  setTypeFilter(filter: DocumentTypeFilter): void {

    this.typeFilter = filter;

  }



  toggleSort(): void {

    this.sortRecent = !this.sortRecent;

  }



  openDocument(doc: UserDocumentItem): void {

    if (doc.sessionId) {

      void this.router.navigate(['/chat'], { queryParams: { session: doc.sessionId } });

      return;

    }

    if (doc.historyId && doc.trackingNumber) {

      void this.router.navigate(['/history'], { queryParams: { tracking: doc.trackingNumber } });

      return;

    }

    void this.router.navigateByUrl('/history');

  }



  downloadDocument(event: Event, doc: UserDocumentItem): void {

    event.stopPropagation();

    this.downloading = true;

    const lang = this.i18n.toBackendCode() as 'fr' | 'en' | 'ar';

    const spec = buildDocumentDownloadSpec({
      type: doc.type,
      trackingNumber: doc.trackingNumber,
      sessionId: doc.sessionId,
      title: doc.title,
      sourceText: doc.sourceText,
    });

    this.history.downloadFromSpec(spec, lang).subscribe({

      next: () => {

        this.downloading = false;

      },

      error: () => {

        this.downloading = false;

        this.error = this.i18n.t('history.exportError');

      },

    });

  }



  exportAll(): void {

    this.downloading = true;

    const lang = this.i18n.toBackendCode() as 'fr' | 'en' | 'ar';

    this.history.downloadExcel({ lang, limit: 500, includeEvents: true }).subscribe({

      next: () => {

        this.downloading = false;

      },

      error: () => {

        this.downloading = false;

        this.error = this.i18n.t('history.exportError');

      },

    });

  }



  generateFirstReport(): void {
    void this.router.navigateByUrl('/chat');
  }

  toggleDocMenu(event: Event, docId: string): void {

    event.stopPropagation();

    this.openMenuDocId = this.openMenuDocId === docId ? null : docId;

  }



  isDocMenuOpen(docId: string): boolean {

    return this.openMenuDocId === docId;

  }



  openRenameDoc(event: Event, doc: UserDocumentItem): void {

    event.stopPropagation();

    this.openMenuDocId = null;

    this.targetDoc = doc;

    this.renameDraft = doc.title;

    this.renameModalOpen = true;

  }



  saveRenameDoc(): void {

    if (!this.targetDoc) {

      return;

    }

    const cleaned = this.renameDraft.trim();

    if (!cleaned) {

      return;

    }

    this.titleOverrides.set(this.targetDoc.id, cleaned);

    this.closeDocModals();

  }



  openDeleteDoc(event: Event, doc: UserDocumentItem): void {

    event.stopPropagation();

    this.openMenuDocId = null;

    this.targetDoc = doc;

    this.deleteModalOpen = true;

  }



  confirmDeleteDoc(): void {

    if (!this.targetDoc) {

      return;

    }

    this.hiddenDocIds.add(this.targetDoc.id);

    this.closeDocModals();

  }



  moveDocToFolder(event: Event, doc: UserDocumentItem): void {

    event.stopPropagation();

    this.openMenuDocId = null;

    if (doc.sessionId) {

      this.sidebarBridge.navigateAction(String(doc.sessionId), 'move');

      return;

    }

    void this.router.navigateByUrl('/chat');

  }



  closeDocModals(): void {

    this.renameModalOpen = false;

    this.deleteModalOpen = false;

    this.targetDoc = null;

    this.renameDraft = '';

  }



  ngOnDestroy(): void {
    this.subs.unsubscribe();
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



  private buildDocuments(rows: HistoryItem[]): UserDocumentItem[] {

    const docs: UserDocumentItem[] = [];

    const seen = new Set<string>();



    for (const row of rows) {

      const blob = `${row.user_question} ${row.bot_response}`;

      const type = classifyDocumentBlob(blob);

      if (!type) {

        continue;

      }

      const key = `${type}-${row.tracking_number}-${row.session_id ?? row.id}`;

      if (seen.has(key)) {

        continue;

      }

      seen.add(key);

      docs.push({

        id: key,

        title: this.documentTitle(type, row.tracking_number),

        type,

        trackingNumber: row.tracking_number,

        createdAt: row.created_at,

        sessionId: row.session_id ?? undefined,

        historyId: row.id,

        fileSizeKb: this.estimateFileSize(type, key),

        sourceText: blob,

      });

    }



    for (const session of this.sessions) {

      const title = session.title;

      const type = classifyDocumentBlob(title);

      if (!type) {

        continue;

      }

      const key = `session-${session.id}`;

      if (seen.has(key)) {

        continue;

      }

      seen.add(key);

      docs.push({

        id: key,

        title: session.title,

        type,

        createdAt: session.updated_at,

        sessionId: session.id,

        fileSizeKb: this.estimateFileSize(type, key),

        sourceText: title,

      });

    }



    return docs.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  }



  private estimateFileSize(type: UserDocumentItem['type'], seed: string): number {
    const base = type === 'export' ? 48 : type === 'proof' ? 156 : 88;
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
      hash = (hash + seed.charCodeAt(i)) % 97;
    }
    return base + hash;
  }

  private documentTitle(type: UserDocumentItem['type'], trackingNumber: string): string {

    const prefix = this.typeLabel(type);

    return trackingNumber ? `${prefix} — ${trackingNumber}` : prefix;

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


