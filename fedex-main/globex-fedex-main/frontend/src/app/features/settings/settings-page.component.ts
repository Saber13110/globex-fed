import { CommonModule } from '@angular/common';
import { Component, ElementRef, HostListener, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import QRCode from 'qrcode';

import { LangCode } from '../../core/i18n/i18n.types';
import { I18nService } from '../../core/i18n/i18n.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import {
  ActiveSession,
  AuthService,
  PreferenceProfileStructured,
  PreferenceTone,
} from '../../core/services/auth.service';
import { UserPreferencesService } from '../../core/services/user-preferences.service';

type SettingsTab = 'profile' | 'security' | 'appearance' | 'language';

type NavIcon = 'user' | 'shield' | 'palette' | 'languages';

interface SettingsNavItem {
  tab: SettingsTab;
  labelKey: string;
  icon: NavIcon;
}

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.scss',
})
export class SettingsPageComponent implements OnInit {
  @ViewChild('langNavTrigger') langNavTrigger?: ElementRef<HTMLButtonElement>;
  @ViewChild('langFlyoutPanel') langFlyoutPanel?: ElementRef<HTMLElement>;

  tab: SettingsTab = 'profile';
  langFlyoutOpen = false;
  langFlyoutTop = 0;
  langFlyoutLeft = 0;
  sidebarOpen = false;
  langSearchQuery = '';
  saved = false;
  accountActionMessage = '';
  organizationId = '';
  activeSessions: ActiveSession[] = [];
  deleteConfirmOpen = false;
  passwordModalOpen = false;
  userRole = '';
  userEmail = '';
  memberSince: Date | null = null;
  lastLogin: Date | null = null;
  qrImageUrl: string | null = null;
  qrPayload: string | null = null;
  qrCanUse = false;
  qrHasActive = false;
  qrLoading = false;

  fullName = '';
  displayName = '';
  jobDescription = '';
  responsePreferences = '';
  prefTone: PreferenceTone = 'professional';
  prefCiteFedex = true;
  prefShortAnswers = false;
  prefFreeNotes = '';
  preferencesActive = '';
  preferencesPending = false;
  preferencesStatusMessage = '';
  preferencesError = '';
  preferencesSubmitting = false;
  language = 'Français';
  responseCompletionNotifications = false;
  responseLength: 'short' | 'medium' | 'detailed' = 'medium';
  notifyTrackingUpdates = true;
  notifyAiMentions = true;
  notifyExportReady = true;
  notifyDeliveryUpdates = true;
  notifySecurityAlerts = true;
  dateFormat: 'mdy' | 'dmy' | 'ymd' = 'dmy';
  timeFormat: '12h' | '24h' = '24h';
  colorMode: 'light' | 'auto' | 'dark' = 'auto';
  backgroundAnimation: 'on' | 'auto' | 'off' = 'auto';
  chatFont: 'default' | 'sans' | 'system' | 'dyslexic' = 'default';
  accentColor: 'fedex' | 'purple' | 'orange' | 'blue' = 'fedex';
  chatDensity: 'compact' | 'comfortable' | 'large' = 'comfortable';
  dataSharingEnabled = false;
  memoryEnabled = true;
  telemetryEnabled = true;
  billingPlan: 'free' | 'team' | 'enterprise' = 'free';
  billingCycle: 'monthly' | 'yearly' = 'monthly';
  invoicesEmail = '';
  canUseFiles = true;
  canUseWebSearch = true;
  canUseCodeExecution = true;
  connectorsGoogleDrive = false;
  connectorsSlack = false;
  connectorsNotion = false;
  claudeCodeAutoRun = false;
  claudeCodeConfirmCommands = true;
  avatarVariant = 0;

  readonly primaryNav: SettingsNavItem[] = [
    { tab: 'profile', labelKey: 'settings.nav.profile', icon: 'user' },
    { tab: 'security', labelKey: 'settings.nav.security', icon: 'shield' },
    { tab: 'appearance', labelKey: 'settings.nav.appearance', icon: 'palette' },
    { tab: 'language', labelKey: 'settings.nav.language', icon: 'languages' },
  ];

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly prefs: UserPreferencesService,
    private readonly auth: AuthService,
    private readonly i18n: I18nService,
  ) {}

  get languageOptions() {
    return this.i18n.languageOptions;
  }

  get toneOptions(): { value: PreferenceTone; labelKey: string }[] {
    return [
      { value: 'professional', labelKey: 'settings.tone.professional' },
      { value: 'friendly', labelKey: 'settings.tone.friendly' },
      { value: 'formal', labelKey: 'settings.tone.technical' },
      { value: 'concise', labelKey: 'settings.tone.concise' },
    ];
  }

  get responseLengthOptions(): { value: 'short' | 'medium' | 'detailed'; labelKey: string }[] {
    return [
      { value: 'short', labelKey: 'settings.responseLength.short' },
      { value: 'medium', labelKey: 'settings.responseLength.medium' },
      { value: 'detailed', labelKey: 'settings.responseLength.detailed' },
    ];
  }

  get jobOptions(): string[] {
    return [
      this.i18n.t('settings.jobPlaceholder'),
      this.i18n.t('settings.job.developer'),
      this.i18n.t('settings.job.pm'),
      this.i18n.t('settings.job.support'),
      this.i18n.t('settings.job.logistics'),
      this.i18n.t('settings.job.other'),
    ];
  }

  get username(): string {
    const email = this.userEmail.trim();
    if (!email.includes('@')) {
      return email || '—';
    }
    return email.split('@')[0];
  }

  get animationsEnabled(): boolean {
    return this.backgroundAnimation !== 'off';
  }

  get filteredLanguageOptions() {
    const q = this.langSearchQuery.trim().toLowerCase();
    if (!q) {
      return this.languageOptions;
    }
    return this.languageOptions.filter((opt) => {
      const label = this.i18n.t(opt.menuLabelKey).toLowerCase();
      return label.includes(q) || opt.code.includes(q);
    });
  }

  get popularLanguageCodes(): LangCode[] {
    return ['en', 'fr', 'ar'];
  }

  get popularLanguageOptions() {
    return this.languageOptions.filter((opt) => this.popularLanguageCodes.includes(opt.code));
  }

  ngOnInit(): void {
    this.route.paramMap.subscribe((params) => {
      const rawTab = params.get('tab');
      const normalized = this.normalizeTab(rawTab);
      if (rawTab !== normalized) {
        void this.router.navigate(['/settings', normalized], { replaceUrl: true });
        return;
      }
      this.tab = normalized;
      if (this.tab === 'security') {
        this.loadQrLogin();
      }
      if (this.tab !== 'language') {
        this.langFlyoutOpen = false;
      }
    });

    const current = this.prefs.read();
    this.applyLocalPrefs(current);
    if (!this.jobDescription) {
      this.jobDescription = this.jobOptions[0];
    }

    this.loadServerPreferences();

    this.auth.me().subscribe({
      next: (profile) => {
        this.userRole = profile.role;
        this.userEmail = profile.email;
        this.prefs.syncFromAuthProfile(profile);
        this.i18n.syncFromAuthProfile(profile.preferred_language);
        this.applyLocalPrefs(this.prefs.read());
      },
      error: () => undefined,
    });
    this.loadAccountOverview();
  }

  get avatarInitial(): string {
    const value = (this.fullName || this.displayName || 'A').trim();
    return value ? value.charAt(0).toUpperCase() : 'A';
  }

  get avatarVariantClass(): string {
    return `sp-avatar--variant-${this.avatarVariant % 6}`;
  }

  get prefFreeNotesCount(): number {
    return this.prefFreeNotes.length;
  }

  goTo(tab: SettingsTab): void {
    this.sidebarOpen = false;
    if (tab !== 'language') {
      this.langFlyoutOpen = false;
    }
    void this.router.navigate(['/settings', tab]);
    if (tab === 'security') {
      this.loadQrLogin();
    }
  }

  goToLanguage(event: Event): void {
    event.stopPropagation();
    this.tab = 'language';
    void this.router.navigate(['/settings', 'language']);
    this.langFlyoutOpen = !this.langFlyoutOpen;
    if (this.langFlyoutOpen) {
      setTimeout(() => this.updateLangFlyoutPosition(), 0);
    }
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  closeSidebar(): void {
    this.sidebarOpen = false;
  }

  isActiveLang(code: LangCode): boolean {
    return this.i18n.langCode() === code;
  }

  selectLanguage(code: LangCode, event?: Event): void {
    event?.stopPropagation();
    if (this.i18n.langCode() === code) {
      return;
    }
    this.i18n.setLang(code);
    this.language = this.i18n.toDisplayName(code);
    this.syncLanguageToBackend();
    this.persistAll();
  }

  langFlag(code: LangCode): string {
    const flags: Record<LangCode, string> = { en: '🇬🇧', fr: '🇫🇷', ar: '🇸🇦' };
    return flags[code] || '🌐';
  }

  isCurrentSession(index: number): boolean {
    return index === 0;
  }

  sessionBrowserLabel(session: ActiveSession): string {
    return `${session.browser} · ${session.machine}`;
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as Node;
    if (this.langNavTrigger?.nativeElement.contains(target) || this.langFlyoutPanel?.nativeElement.contains(target)) {
      return;
    }
    this.langFlyoutOpen = false;
  }

  @HostListener('window:resize')
  onWindowResize(): void {
    if (this.langFlyoutOpen) {
      this.updateLangFlyoutPosition();
    }
    if (window.innerWidth > 960) {
      this.sidebarOpen = false;
    }
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.sidebarOpen = false;
    this.langFlyoutOpen = false;
    this.deleteConfirmOpen = false;
    this.passwordModalOpen = false;
  }

  private updateLangFlyoutPosition(): void {
    const el = this.langNavTrigger?.nativeElement;
    if (!el) {
      return;
    }
    const rect = el.getBoundingClientRect();
    const flyoutWidth = 260;
    const gap = 10;
    let left = rect.right + gap;
    const maxLeft = window.innerWidth - flyoutWidth - 12;
    if (left > maxLeft) {
      left = Math.max(12, rect.left - flyoutWidth - gap);
    }
    let top = rect.top;
    const maxTop = window.innerHeight - 280;
    if (top > maxTop) {
      top = maxTop;
    }
    this.langFlyoutTop = top;
    this.langFlyoutLeft = left;
  }

  loadQrLogin(): void {
    this.qrLoading = true;
    this.auth.getMyQrLogin().subscribe({
      next: (res) => {
        this.qrCanUse = res.can_use_qr;
        this.qrHasActive = res.has_active_qr;
        if (res.payload) {
          this.qrPayload = res.payload;
          void this.renderQrImage(res.payload);
        } else {
          this.qrImageUrl = null;
          this.qrPayload = null;
        }
        this.qrLoading = false;
      },
      error: () => {
        this.qrLoading = false;
      },
    });
  }

  regenerateQrLogin(): void {
    this.qrLoading = true;
    this.auth.regenerateMyQrLogin().subscribe({
      next: (res) => {
        if (res.payload) {
          this.qrPayload = res.payload;
          void this.renderQrImage(res.payload);
        }
        this.qrHasActive = res.has_active_qr;
        this.qrCanUse = res.can_use_qr;
        this.qrLoading = false;
        this.accountActionMessage = this.i18n.t('settings.qrRegenerated');
      },
      error: () => {
        this.qrLoading = false;
        this.accountActionMessage = this.i18n.t('settings.qrRegenerateFailed');
      },
    });
  }

  private async renderQrImage(payload: string): Promise<void> {
    this.qrPayload = payload;
    this.qrImageUrl = await QRCode.toDataURL(payload, {
      width: 260,
      margin: 2,
      color: { dark: '#5E17EB', light: '#FFFFFF' },
    });
  }

  copyQrPayload(): void {
    if (!this.qrPayload) {
      this.accountActionMessage = this.i18n.t('settings.qrCopyFirst');
      return;
    }
    void navigator.clipboard.writeText(this.qrPayload).then(() => {
      this.accountActionMessage = this.i18n.t('settings.qrLoginCopied');
    });
  }

  downloadQrImage(): void {
    if (!this.qrImageUrl) {
      this.accountActionMessage = this.i18n.t('settings.qrCopyFirst');
      return;
    }
    const link = document.createElement('a');
    link.href = this.qrImageUrl;
    link.download = 'fedex-qr-login.png';
    link.click();
  }

  saveProfile(): void {
    this.persistAll();
  }

  saveAi(): void {
    this.persistAll();
  }

  saveNotifications(): void {
    this.persistAll();
  }

  saveAppearance(): void {
    this.persistAll();
  }

  saveLanguageSettings(): void {
    this.i18n.setFromDisplayName(this.language);
    this.syncLanguageToBackend();
    this.persistAll();
  }

  savePrivacy(): void {
    this.persistAll();
  }

  saveBilling(): void {
    this.persistAll();
  }

  saveCapabilities(): void {
    this.persistAll();
  }

  saveConnectors(): void {
    this.persistAll();
  }

  saveClaudeCode(): void {
    this.persistAll();
  }

  openPasswordModal(): void {
    this.passwordModalOpen = true;
  }

  closePasswordModal(): void {
    this.passwordModalOpen = false;
  }

  logoutAll(): void {
    this.accountActionMessage = '';
    this.auth.logoutAll().subscribe({
      next: () => {
        this.auth.logout();
      },
      error: () => {
        this.accountActionMessage = this.i18n.t('settings.logoutAllFailed');
      },
    });
  }

  openDeleteConfirmation(): void {
    this.deleteConfirmOpen = true;
  }

  closeDeleteConfirmation(): void {
    this.deleteConfirmOpen = false;
  }

  confirmDeleteAccount(): void {
    this.accountActionMessage = '';
    this.auth.deleteAccount().subscribe({
      next: () => {
        this.deleteConfirmOpen = false;
        this.auth.logout();
      },
      error: () => {
        this.accountActionMessage = this.i18n.t('settings.deleteFailed');
      },
    });
  }

  toggleResponseCompletionNotifications(): void {
    this.responseCompletionNotifications = !this.responseCompletionNotifications;
    if (this.responseCompletionNotifications && typeof Notification !== 'undefined' && Notification.permission === 'default') {
      void Notification.requestPermission();
    }
    this.persistAll();
  }

  togglePref(key: 'notifyTrackingUpdates' | 'notifyAiMentions' | 'notifyExportReady' | 'notifyDeliveryUpdates' | 'notifySecurityAlerts'): void {
    this[key] = !this[key];
    this.persistAll();
  }

  togglePrivacy(key: 'dataSharingEnabled' | 'memoryEnabled' | 'telemetryEnabled'): void {
    this[key] = !this[key];
    this.persistAll();
  }

  toggleCapability(key: 'canUseFiles' | 'canUseWebSearch' | 'canUseCodeExecution'): void {
    this[key] = !this[key];
    this.persistAll();
  }

  toggleConnector(key: 'connectorsGoogleDrive' | 'connectorsSlack' | 'connectorsNotion'): void {
    this[key] = !this[key];
    this.persistAll();
  }

  toggleClaudeCode(key: 'claudeCodeAutoRun' | 'claudeCodeConfirmCommands'): void {
    this[key] = !this[key];
    this.persistAll();
  }

  setPrefTone(tone: PreferenceTone): void {
    this.prefTone = tone;
  }

  setColorMode(mode: 'light' | 'auto' | 'dark'): void {
    this.colorMode = mode;
    this.prefs.updateTheme(mode);
    this.persistAll();
  }

  setBackgroundAnimation(mode: 'on' | 'auto' | 'off'): void {
    this.backgroundAnimation = mode;
    this.prefs.updateAnimations(mode);
    this.persistAll();
  }

  toggleAnimations(): void {
    this.backgroundAnimation = this.animationsEnabled ? 'off' : 'auto';
    this.prefs.updateAnimations(this.backgroundAnimation);
    this.persistAll();
  }

  setChatFont(font: 'default' | 'sans' | 'system' | 'dyslexic'): void {
    this.chatFont = font;
    this.prefs.updateFont(font);
    this.persistAll();
  }

  setAccentColor(color: 'fedex' | 'purple' | 'orange' | 'blue'): void {
    this.accentColor = color;
    this.prefs.updateAccentColor(color);
    this.persistAll();
  }

  setChatDensity(density: 'compact' | 'comfortable' | 'large'): void {
    this.chatDensity = density;
    this.prefs.updateDensity(density);
    this.persistAll();
  }

  setResponseLength(length: 'short' | 'medium' | 'detailed'): void {
    this.responseLength = length;
    this.persistAll();
  }

  setDateFormat(format: 'mdy' | 'dmy' | 'ymd'): void {
    this.dateFormat = format;
    this.persistAll();
  }

  setTimeFormat(format: '12h' | '24h'): void {
    this.timeFormat = format;
    this.persistAll();
  }

  setBillingPlan(plan: 'free' | 'team' | 'enterprise'): void {
    this.billingPlan = plan;
    this.persistAll();
  }

  setBillingCycle(cycle: 'monthly' | 'yearly'): void {
    this.billingCycle = cycle;
    this.persistAll();
  }

  randomizeAvatar(): void {
    this.avatarVariant = Math.floor(Math.random() * 6);
    this.persistAll();
  }

  togglePrefCiteFedex(): void {
    this.prefCiteFedex = !this.prefCiteFedex;
  }

  togglePrefShortAnswers(): void {
    this.prefShortAnswers = !this.prefShortAnswers;
  }

  private normalizeTab(tab: string | null): SettingsTab {
    const legacy: Record<string, SettingsTab> = {
      general: 'profile',
      account: 'security',
      ai: 'profile',
      notifications: 'profile',
      privacy: 'profile',
      billing: 'profile',
      capabilities: 'profile',
      connectors: 'profile',
      'claude-code': 'profile',
    };
    if (tab && legacy[tab]) {
      return legacy[tab];
    }
    const allowed: SettingsTab[] = ['profile', 'security', 'appearance', 'language'];
    if (tab && allowed.includes(tab as SettingsTab)) {
      return tab as SettingsTab;
    }
    return 'profile';
  }

  private syncLanguageToBackend(): void {
    if (!this.auth.token()) {
      return;
    }
    this.auth.updateProfile({ preferred_language: this.i18n.toBackendCode() }).subscribe({
      error: () => undefined,
    });
  }

  private applyStructuredProfile(profile: PreferenceProfileStructured | null | undefined): void {
    if (!profile) {
      return;
    }
    this.prefTone = profile.tone;
    this.prefCiteFedex = profile.cite_fedex;
    this.prefShortAnswers = profile.short_answers;
    this.prefFreeNotes = profile.free_notes || '';
  }

  loadServerPreferences(): void {
    if (!this.auth.token()) {
      return;
    }
    this.auth.getMyPreferences().subscribe({
      next: (state) => {
        this.preferencesActive = state.active || '';
        if (state.pending_structured) {
          this.applyStructuredProfile(state.pending_structured);
        } else if (state.active_structured) {
          this.applyStructuredProfile(state.active_structured);
        }
        if (state.pending) {
          this.responsePreferences = state.pending;
          this.preferencesPending = true;
          this.preferencesStatusMessage = this.i18n.t('settings.prefsPending');
        } else {
          this.responsePreferences = state.active || this.responsePreferences;
          this.preferencesPending = false;
          if (state.rejection_note) {
            this.preferencesStatusMessage = this.i18n.t('settings.prefsRejected', {
              note: state.rejection_note,
            });
          } else {
            this.preferencesStatusMessage = state.active ? this.i18n.t('settings.prefsActive') : '';
          }
        }
      },
      error: () => undefined,
    });
  }

  submitPreferencesForReview(): void {
    const notes = this.prefFreeNotes.trim();
    if (!notes && !this.prefTone) {
      this.preferencesError = this.i18n.t('settings.prefsEmpty');
      return;
    }
    this.preferencesSubmitting = true;
    this.preferencesError = '';
    this.preferencesStatusMessage = '';
    this.auth
      .submitPreferences({
        tone: this.prefTone,
        cite_fedex: this.prefCiteFedex,
        short_answers: this.prefShortAnswers,
        free_notes: notes,
      })
      .subscribe({
        next: () => {
          this.preferencesSubmitting = false;
          this.preferencesPending = true;
          this.preferencesStatusMessage = this.i18n.t('settings.prefsSubmitted');
          this.loadServerPreferences();
        },
        error: (err) => {
          this.preferencesSubmitting = false;
          const detail = err?.error?.detail;
          this.preferencesError = typeof detail === 'string' ? detail : this.i18n.t('settings.prefsSubmitFailed');
        },
      });
  }

  private applyLocalPrefs(current: ReturnType<UserPreferencesService['read']>): void {
    this.fullName = current.fullName;
    this.displayName = current.displayName;
    this.jobDescription = current.jobDescription;
    this.responsePreferences = current.responsePreferences;
    this.language = current.language;
    this.responseCompletionNotifications = current.responseCompletionNotifications;
    this.responseLength = current.responseLength;
    this.notifyTrackingUpdates = current.notifyTrackingUpdates;
    this.notifyAiMentions = current.notifyAiMentions;
    this.notifyExportReady = current.notifyExportReady;
    this.notifyDeliveryUpdates = current.notifyDeliveryUpdates;
    this.notifySecurityAlerts = current.notifySecurityAlerts;
    this.dateFormat = current.dateFormat;
    this.timeFormat = current.timeFormat;
    this.colorMode = current.colorMode;
    this.backgroundAnimation = current.backgroundAnimation;
    this.chatFont = current.chatFont;
    this.accentColor = current.accentColor;
    this.chatDensity = current.chatDensity;
    this.dataSharingEnabled = current.dataSharingEnabled;
    this.memoryEnabled = current.memoryEnabled;
    this.telemetryEnabled = current.telemetryEnabled;
    this.billingPlan = current.billingPlan;
    this.billingCycle = current.billingCycle;
    this.invoicesEmail = current.invoicesEmail;
    this.canUseFiles = current.canUseFiles;
    this.canUseWebSearch = current.canUseWebSearch;
    this.canUseCodeExecution = current.canUseCodeExecution;
    this.connectorsGoogleDrive = current.connectorsGoogleDrive;
    this.connectorsSlack = current.connectorsSlack;
    this.connectorsNotion = current.connectorsNotion;
    this.claudeCodeAutoRun = current.claudeCodeAutoRun;
    this.claudeCodeConfirmCommands = current.claudeCodeConfirmCommands;
    this.avatarVariant = current.avatarVariant;
  }

  private persistAll(): void {
    this.prefs.write({
      fullName: this.fullName.trim() || 'ana',
      displayName: this.displayName.trim() || this.fullName.trim() || 'ana',
      jobDescription: this.jobDescription.trim(),
      responsePreferences: this.responsePreferences.trim(),
      language: this.language.trim() || 'Français',
      responseCompletionNotifications: this.responseCompletionNotifications,
      sendMessageNotifications: false,
      responseLength: this.responseLength,
      notifyTrackingUpdates: this.notifyTrackingUpdates,
      notifyAiMentions: this.notifyAiMentions,
      notifyExportReady: this.notifyExportReady,
      notifyDeliveryUpdates: this.notifyDeliveryUpdates,
      notifySecurityAlerts: this.notifySecurityAlerts,
      dateFormat: this.dateFormat,
      timeFormat: this.timeFormat,
      colorMode: this.colorMode,
      backgroundAnimation: this.backgroundAnimation,
      chatFont: this.chatFont,
      accentColor: this.accentColor,
      chatDensity: this.chatDensity,
      dataSharingEnabled: this.dataSharingEnabled,
      memoryEnabled: this.memoryEnabled,
      telemetryEnabled: this.telemetryEnabled,
      billingPlan: this.billingPlan,
      billingCycle: this.billingCycle,
      invoicesEmail: this.invoicesEmail.trim(),
      canUseFiles: this.canUseFiles,
      canUseWebSearch: this.canUseWebSearch,
      canUseCodeExecution: this.canUseCodeExecution,
      connectorsGoogleDrive: this.connectorsGoogleDrive,
      connectorsSlack: this.connectorsSlack,
      connectorsNotion: this.connectorsNotion,
      claudeCodeAutoRun: this.claudeCodeAutoRun,
      claudeCodeConfirmCommands: this.claudeCodeConfirmCommands,
      avatarVariant: this.avatarVariant,
    });
    this.saved = true;
    setTimeout(() => {
      this.saved = false;
    }, 1800);
  }

  private loadAccountOverview(): void {
    this.auth.accountOverview().subscribe({
      next: (res) => {
        this.organizationId = res.organization_id;
        this.activeSessions = res.sessions;
        if (res.sessions.length) {
          const sorted = [...res.sessions].sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
          );
          this.memberSince = new Date(sorted[0].created_at);
          this.lastLogin = new Date(res.sessions[0].updated_at);
        }
      },
      error: () => {
        this.organizationId = '';
        this.activeSessions = [];
      },
    });
  }
}
