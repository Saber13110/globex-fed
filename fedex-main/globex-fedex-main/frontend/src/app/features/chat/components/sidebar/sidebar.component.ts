import { CommonModule, DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  ViewChild,
  inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { I18nService } from '../../../../core/i18n/i18n.service';
import { LangCode } from '../../../../core/i18n/i18n.types';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AuthService } from '../../../../core/services/auth.service';
import { UserPreferencesService } from '../../../../core/services/user-preferences.service';
import { Conversation } from '../chat-item/chat-item.component';

export interface SidebarProject {
  id: number;
  name: string;
  count: number;
  isActive: boolean;
}

export interface SidebarRecentGroup {
  label: string;
  conversations: Conversation[];
}

export interface SidebarFolderShortcut {
  id: string;
  labelKey: string;
  count: number;
}

export type SidebarActiveNav = 'home' | 'history' | 'documents' | 'notifications';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, TranslatePipe],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SidebarComponent implements OnChanges {
  readonly i18n = inject(I18nService);
  private readonly router = inject(Router);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly hostRef = inject(ElementRef<HTMLElement>);

  @Input() collapsed = false;
  /** Lien admin : uniquement si explicitement autorisé (jamais sur portail client). */
  @Input() showAdminLink = false;
  @Input() portalMode: 'client' | 'employee' = 'client';
  @Input() language = 'Français';
  @Input() avatarUrl: string | null = null;
  @Input() unreadCount = 0;
  @Input() recentGroups: SidebarRecentGroup[] = [];
  @Input() folderShortcuts: SidebarFolderShortcut[] = [];
  @Input() accountName = '';
  @Input() accountEmail = '';
  @Input() avatarInitial = 'A';
  @Input() avatarClass = '';
  @Input() colorMode: 'light' | 'dark' | 'auto' = 'light';
  @Input() showNotificationDot = false;
  @Input() searchQuery = '';
  @Input() pinnedConversations: Conversation[] = [];
  @Input() recentConversations: Conversation[] = [];
  @Input() projects: SidebarProject[] = [];
  @Input() allChatsActive = true;
  @Input() totalChatsCount = 0;
  @Input() loading = false;
  @Input() activeNav: SidebarActiveNav = 'home';

  @Output() collapseToggle = new EventEmitter<void>();
  @Output() createChat = new EventEmitter<void>();
  @Output() goHome = new EventEmitter<void>();
  @Output() openSearch = new EventEmitter<void>();
  @Output() searchQueryChange = new EventEmitter<string>();
  @Output() openHistory = new EventEmitter<void>();
  @Output() openTrackingHistory = new EventEmitter<void>();
  @Output() createProject = new EventEmitter<void>();
  @Output() selectProject = new EventEmitter<number | null>();
  @Output() selectConversation = new EventEmitter<string>();
  @Output() renameConversation = new EventEmitter<{ id: string; title: string }>();
  @Output() renameConversationRequest = new EventEmitter<string>();
  @Output() togglePinConversation = new EventEmitter<string>();
  @Output() moveConversation = new EventEmitter<string>();
  @Output() deleteConversation = new EventEmitter<string>();
  @Output() openHelp = new EventEmitter<void>();
  @Output() openSettings = new EventEmitter<void>();
  @Output() openNotifications = new EventEmitter<void>();
  @Output() openProfile = new EventEmitter<void>();
  @Output() openDocuments = new EventEmitter<void>();
  @Output() openSupport = new EventEmitter<void>();
  @Output() folderShortcut = new EventEmitter<string>();
  @Output() toggleTheme = new EventEmitter<void>();
  @Output() logout = new EventEmitter<void>();

  @ViewChild('langTrigger') langTrigger?: ElementRef<HTMLButtonElement>;

  accountMenuOpen = false;
  langFlyoutOpen = false;
  langFlyoutTop = 0;
  langFlyoutLeft = 0;
  private langFlyoutCloseTimer: ReturnType<typeof setTimeout> | null = null;
  recentsExpanded = false;
  foldersExpanded = false;
  openConversationMenuId: string | null = null;
  hoveredConversationId: string | null = null;
  displayRecentsList: Conversation[] = [];
  private navigating = false;

  private readonly auth = inject(AuthService);
  private readonly prefs = inject(UserPreferencesService);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['pinnedConversations'] || changes['recentConversations']) {
      this.rebuildRecentsList();
    }
  }

  private rebuildRecentsList(): void {
    const pinned = [...this.pinnedConversations].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    );
    const recent = [...this.recentConversations].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    );
    this.displayRecentsList = [...pinned, ...recent].slice(0, 10);
  }

  setRowHover(conversationId: string): void {
    this.hoveredConversationId = conversationId;
  }

  clearRowHover(conversationId: string): void {
    if (this.hoveredConversationId === conversationId) {
      this.hoveredConversationId = null;
    }
  }

  isRowHovered(conversationId: string): boolean {
    return this.hoveredConversationId === conversationId;
  }

  showConversationMenuBtn(conv: Conversation): boolean {
    return (
      conv.isActive === true ||
      this.isRowHovered(conv.id) ||
      this.isConversationMenuOpen(conv.id)
    );
  }

  isConversationMenuOpen(conversationId: string): boolean {
    return this.openConversationMenuId === conversationId;
  }

  toggleConversationMenu(event: Event, conversationId: string): void {
    event.stopPropagation();
    event.preventDefault();
    this.openConversationMenuId =
      this.openConversationMenuId === conversationId ? null : conversationId;
    this.cdr.markForCheck();
  }

  closeConversationMenu(): void {
    this.openConversationMenuId = null;
  }

  onRenameRequest(event: Event, conversationId: string): void {
    event.stopPropagation();
    this.closeConversationMenu();
    this.renameConversationRequest.emit(conversationId);
  }

  onMenuPin(event: Event, conversationId: string): void {
    event.stopPropagation();
    this.closeConversationMenu();
    this.togglePinConversation.emit(conversationId);
  }

  onMenuMove(event: Event, conversationId: string): void {
    event.stopPropagation();
    this.closeConversationMenu();
    this.moveConversation.emit(conversationId);
  }

  onMenuDelete(event: Event, conversationId: string): void {
    event.stopPropagation();
    this.closeConversationMenu();
    this.deleteConversation.emit(conversationId);
  }

  toggleRecentsSection(event: Event): void {
    event.stopPropagation();
    this.recentsExpanded = !this.recentsExpanded;
    this.cdr.markForCheck();
  }

  toggleFoldersSection(event: Event): void {
    event.stopPropagation();
    this.foldersExpanded = !this.foldersExpanded;
    this.cdr.markForCheck();
  }

  get isDarkMode(): boolean {
    return this.colorMode === 'dark';
  }

  @HostListener('document:click', ['$event'])
  closeMenusOnOutsideClick(event: MouseEvent): void {
    const target = event.target as Node | null;
    if (!target) {
      return;
    }
    const root = this.hostRef.nativeElement;
    if (!root.contains(target)) {
      this.accountMenuOpen = false;
      this.closeLangFlyout();
      this.closeConversationMenu();
      this.cdr.markForCheck();
      return;
    }
    const inAccount = (target as HTMLElement).closest('.ux-sidebar__account-wrap');
    const inConvMenu = (target as HTMLElement).closest('.ux-sidebar__conv-menu, .ux-sidebar__menu-btn');
    if (!inAccount) {
      this.accountMenuOpen = false;
      this.closeLangFlyout();
    }
    if (!inConvMenu) {
      this.closeConversationMenu();
    }
    this.cdr.markForCheck();
  }

  @HostListener('document:keydown.escape')
  closeMenusOnEscape(): void {
    this.accountMenuOpen = false;
    this.closeLangFlyout();
    this.closeConversationMenu();
  }

  toggleAccountMenu(event: Event): void {
    event.stopPropagation();
    this.accountMenuOpen = !this.accountMenuOpen;
    if (!this.accountMenuOpen) {
      this.closeLangFlyout();
    } else {
      queueMicrotask(() => {
        if (this.langFlyoutOpen) {
          this.updateLangFlyoutPosition();
        }
      });
    }
    this.cdr.markForCheck();
  }

  openLangFlyout(): void {
    if (!this.accountMenuOpen) {
      return;
    }
    this.cancelCloseLangFlyout();
    this.langFlyoutOpen = true;
    this.updateLangFlyoutPosition();
  }

  private updateLangFlyoutPosition(): void {
    const el = this.langTrigger?.nativeElement;
    if (!el) {
      return;
    }
    const rect = el.getBoundingClientRect();
    const flyoutWidth = 228;
    const gap = 8;
    let left = rect.right + gap;
    const maxLeft = window.innerWidth - flyoutWidth - 12;
    if (left > maxLeft) {
      left = Math.max(12, rect.left - flyoutWidth - gap);
    }
    let top = rect.top;
    const maxTop = window.innerHeight - 160;
    if (top > maxTop) {
      top = maxTop;
    }
    this.langFlyoutTop = top;
    this.langFlyoutLeft = left;
  }

  scheduleCloseLangFlyout(): void {
    this.cancelCloseLangFlyout();
    this.langFlyoutCloseTimer = setTimeout(() => {
      this.langFlyoutOpen = false;
      this.langFlyoutCloseTimer = null;
    }, 320);
  }

  cancelCloseLangFlyout(): void {
    if (this.langFlyoutCloseTimer !== null) {
      clearTimeout(this.langFlyoutCloseTimer);
      this.langFlyoutCloseTimer = null;
    }
  }

  closeLangFlyout(): void {
    this.cancelCloseLangFlyout();
    this.langFlyoutOpen = false;
  }

  toggleLangFlyout(event: Event): void {
    event.stopPropagation();
    this.langFlyoutOpen = !this.langFlyoutOpen;
    if (this.langFlyoutOpen) {
      this.updateLangFlyoutPosition();
    }
  }

  @HostListener('window:resize')
  onWindowResize(): void {
    if (this.langFlyoutOpen) {
      this.updateLangFlyoutPosition();
    }
  }

  onThemeClick(event: Event): void {
    event.stopPropagation();
    this.toggleTheme.emit();
  }

  selectLanguage(code: LangCode, event: Event): void {
    event.stopPropagation();
    if (this.i18n.langCode() === code) {
      return;
    }
    this.i18n.setLang(code);
    const current = this.prefs.read();
    this.prefs.write({ ...current, language: this.i18n.toDisplayName(code) });
    if (this.auth.token()) {
      this.auth.updateProfile({ preferred_language: code }).subscribe({
        error: () => undefined,
      });
    }
  }

  isActiveLang(code: LangCode): boolean {
    return this.i18n.langCode() === code;
  }

  openHelpFromMenu(event: Event): void {
    event.stopPropagation();
    this.closeLangFlyout();
    this.accountMenuOpen = false;
    void this.router.navigateByUrl('/help');
  }

  openSettingsFromMenu(event: Event): void {
    event.stopPropagation();
    this.closeLangFlyout();
    this.accountMenuOpen = false;
    void this.router.navigateByUrl('/settings/profile');
  }

  openProfileFromMenu(event: Event): void {
    event.stopPropagation();
    this.closeLangFlyout();
    this.accountMenuOpen = false;
    void this.router.navigateByUrl('/settings/profile');
  }

  openAdminFromMenu(event: Event): void {
    event.stopPropagation();
    this.accountMenuOpen = false;
    void this.router.navigateByUrl('/admin');
  }

  navigateHome(event: Event): void {
    event.stopPropagation();
    if (this.activeNav === 'home') {
      this.goHome.emit();
      return;
    }
    this.navigateTo('/chat');
  }

  navigateHistory(event: Event): void {
    event.stopPropagation();
    if (this.activeNav === 'history') {
      this.openTrackingHistory.emit();
      return;
    }
    this.navigateTo('/history');
  }

  navigateNewChat(event: Event): void {
    event.stopPropagation();
    if (this.activeNav === 'home') {
      this.createChat.emit();
      return;
    }
    this.navigateTo('/chat');
  }

  openNotificationsSidebar(event: Event): void {
    event.stopPropagation();
    if (this.activeNav === 'notifications') {
      this.openNotifications.emit();
      return;
    }
    this.navigateTo('/notifications');
  }

  openDocumentsSidebar(event: Event): void {
    event.stopPropagation();
    if (this.activeNav === 'documents') {
      this.openDocuments.emit();
      return;
    }
    this.navigateTo('/documents');
  }

  navigateSearch(event: Event): void {
    event.stopPropagation();
    if (this.activeNav === 'home') {
      this.openSearch.emit();
      return;
    }
    this.navigateTo('/chat');
  }

  selectConversationItem(sessionId: string, event: Event): void {
    event.stopPropagation();
    this.closeConversationMenu();
    if (this.activeNav === 'home') {
      this.selectConversation.emit(sessionId);
      return;
    }
    void this.router.navigate(['/chat'], { queryParams: { session: sessionId.trim() } });
  }

  private navigateTo(url: string): void {
    if (this.navigating) {
      return;
    }
    const current = this.router.url.split('?')[0];
    if (current === url) {
      return;
    }
    this.navigating = true;
    void this.router.navigateByUrl(url).finally(() => {
      this.navigating = false;
      this.cdr.markForCheck();
    });
  }

  openSupportFromMenu(event: Event): void {
    event.stopPropagation();
    this.accountMenuOpen = false;
    void this.router.navigateByUrl('/help?support=1');
  }

  onFolderShortcutClick(id: string, event: Event): void {
    event.stopPropagation();
    this.folderShortcut.emit(id);
  }

  logoutFromMenu(event: Event): void {
    event.stopPropagation();
    this.accountMenuOpen = false;
    this.logout.emit();
  }

  conversationVisual(conv: Conversation): { tone: 'purple' | 'green' | 'orange' | 'amber'; icon: 'box' | 'doc' | 'chart' | 'alert' } {
    const title = conv.title.toLowerCase();
    if (/preuve|proof|pdf|livraison|delivery|pod/.test(title)) {
      return { tone: 'green', icon: 'doc' };
    }
    if (/export|excel|rapport|report|march|historique|history|performance/.test(title)) {
      return { tone: 'orange', icon: 'chart' };
    }
    if (/problème|problem|issue|retard|delay|support|incident/.test(title)) {
      return { tone: 'amber', icon: 'alert' };
    }
    return { tone: 'purple', icon: 'box' };
  }

  recentStatusLabel(conv: Conversation): string {
    const tone = this.conversationVisual(conv).tone;
    const keys: Record<string, string> = {
      green: 'sidebar.recent.status.ready',
      orange: 'sidebar.recent.status.generated',
      amber: 'sidebar.recent.status.support',
      purple: 'sidebar.recent.status.inProgress',
    };
    return this.i18n.t(keys[tone] ?? keys['purple']);
  }

  formatRecentTime(updatedAt: string): string {
    const date = new Date(updatedAt);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86_400_000);
    const locale = this.i18n.langCode() === 'en' ? 'en-US' : this.i18n.langCode() === 'ar' ? 'ar' : 'fr-FR';
    if (diffDays === 0) {
      return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    }
    if (diffDays === 1) {
      return this.i18n.t('sidebar.group.yesterday');
    }
    if (diffDays < 7) {
      return date.toLocaleDateString(locale, { weekday: 'short' });
    }
    return date.toLocaleDateString(locale, { day: '2-digit', month: 'short' });
  }
}
