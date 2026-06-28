import { Injectable, NgZone } from '@angular/core';

export interface UserProfilePreferences {
  fullName: string;
  displayName: string;
  jobDescription: string;
  responsePreferences: string;
  language: string;
  responseCompletionNotifications: boolean;
  sendMessageNotifications: boolean;
  colorMode: 'light' | 'auto' | 'dark';
  backgroundAnimation: 'on' | 'auto' | 'off';
  chatFont: 'default' | 'sans' | 'system' | 'dyslexic';
  dataSharingEnabled: boolean;
  memoryEnabled: boolean;
  telemetryEnabled: boolean;
  billingPlan: 'free' | 'team' | 'enterprise';
  billingCycle: 'monthly' | 'yearly';
  invoicesEmail: string;
  canUseFiles: boolean;
  canUseWebSearch: boolean;
  canUseCodeExecution: boolean;
  connectorsGoogleDrive: boolean;
  connectorsSlack: boolean;
  connectorsNotion: boolean;
  claudeCodeAutoRun: boolean;
  claudeCodeConfirmCommands: boolean;
  avatarVariant: number;
  responseLength: 'short' | 'medium' | 'detailed';
  notifyTrackingUpdates: boolean;
  notifyAiMentions: boolean;
  notifyExportReady: boolean;
  notifyDeliveryUpdates: boolean;
  notifySecurityAlerts: boolean;
  dateFormat: 'mdy' | 'dmy' | 'ymd';
  timeFormat: '12h' | '24h';
  accentColor: 'fedex' | 'purple' | 'orange' | 'blue';
  chatDensity: 'compact' | 'comfortable' | 'large';
}

const PREFS_KEY = 'globex_user_preferences_v1';

const DEFAULT_PREFS: UserProfilePreferences = {
  fullName: 'ana',
  displayName: 'ana',
  jobDescription: '',
  responsePreferences: '',
  language: 'Français',
  responseCompletionNotifications: false,
  sendMessageNotifications: false,
  colorMode: 'auto',
  backgroundAnimation: 'auto',
  chatFont: 'default',
  dataSharingEnabled: false,
  memoryEnabled: true,
  telemetryEnabled: true,
  billingPlan: 'free',
  billingCycle: 'monthly',
  invoicesEmail: '',
  canUseFiles: true,
  canUseWebSearch: true,
  canUseCodeExecution: true,
  connectorsGoogleDrive: false,
  connectorsSlack: false,
  connectorsNotion: false,
  claudeCodeAutoRun: false,
  claudeCodeConfirmCommands: true,
  avatarVariant: 0,
  responseLength: 'medium',
  notifyTrackingUpdates: true,
  notifyAiMentions: true,
  notifyExportReady: true,
  notifyDeliveryUpdates: true,
  notifySecurityAlerts: true,
  dateFormat: 'dmy',
  timeFormat: '24h',
  accentColor: 'fedex',
  chatDensity: 'comfortable',
};

const ACCENT_PALETTES: Record<UserProfilePreferences['accentColor'], { primary: string; accent: string; soft: string }> = {
  fedex: { primary: '#5E17EB', accent: '#FF6B00', soft: '#8B5CF6' },
  purple: { primary: '#7C3AED', accent: '#A78BFA', soft: '#C4B5FD' },
  orange: { primary: '#FF6B00', accent: '#FB923C', soft: '#FDBA74' },
  blue: { primary: '#2563EB', accent: '#60A5FA', soft: '#93C5FD' },
};

const DENSITY_TOKENS: Record<UserProfilePreferences['chatDensity'], Record<string, string>> = {
  compact: {
    '--chat-list-gap': '0.65rem',
    '--chat-row-gap': '0.55rem',
    '--chat-bubble-pad-y': '0.5rem',
    '--chat-bubble-pad-x': '0.72rem',
    '--chat-bubble-font': '0.875rem',
    '--chat-input-pad-y': '0.55rem',
    '--chat-input-pad-x': '0.85rem',
    '--chat-sidebar-pad': '0.55rem',
  },
  comfortable: {
    '--chat-list-gap': '1.15rem',
    '--chat-row-gap': '0.85rem',
    '--chat-bubble-pad-y': '0.9rem',
    '--chat-bubble-pad-x': '1.04rem',
    '--chat-bubble-font': '0.94rem',
    '--chat-input-pad-y': '0.75rem',
    '--chat-input-pad-x': '1rem',
    '--chat-sidebar-pad': '0.7rem',
  },
  large: {
    '--chat-list-gap': '1.45rem',
    '--chat-row-gap': '1.1rem',
    '--chat-bubble-pad-y': '1.15rem',
    '--chat-bubble-pad-x': '1.25rem',
    '--chat-bubble-font': '1rem',
    '--chat-input-pad-y': '0.95rem',
    '--chat-input-pad-x': '1.15rem',
    '--chat-sidebar-pad': '0.85rem',
  },
};

@Injectable({ providedIn: 'root' })
export class UserPreferencesService {
  private systemThemeMq?: MediaQueryList;
  private reducedMotionMq?: MediaQueryList;
  private boundThemeChange?: () => void;
  private boundMotionChange?: () => void;

  constructor(private readonly zone: NgZone) {
    this.applyToDocument(this.read());
    this.bindSystemListeners();
  }

  getPreferences(): UserProfilePreferences {
    return this.read();
  }

  updateTheme(mode: UserProfilePreferences['colorMode']): void {
    this.savePreferences({ colorMode: mode });
  }

  updateAccentColor(color: UserProfilePreferences['accentColor']): void {
    this.savePreferences({ accentColor: color });
  }

  updateDensity(density: UserProfilePreferences['chatDensity']): void {
    this.savePreferences({ chatDensity: density });
  }

  updateFont(font: UserProfilePreferences['chatFont']): void {
    this.savePreferences({ chatFont: font });
  }

  updateAnimations(mode: UserProfilePreferences['backgroundAnimation']): void {
    this.savePreferences({ backgroundAnimation: mode });
  }

  savePreferences(partial: Partial<UserProfilePreferences>): void {
    this.write({ ...this.read(), ...partial });
  }

  read(): UserProfilePreferences {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) {
      return { ...DEFAULT_PREFS };
    }
    try {
      const parsed = JSON.parse(raw) as Partial<UserProfilePreferences>;
      return this.mergePrefs(parsed);
    } catch {
      return { ...DEFAULT_PREFS };
    }
  }

  write(next: UserProfilePreferences): void {
    localStorage.setItem(PREFS_KEY, JSON.stringify(next));
    this.applyToDocument(next);
  }

  syncFromAuthProfile(profile: { full_name: string; email: string; preferred_language?: string | null }): void {
    const current = this.read();
    const normalizedName = profile.full_name?.trim();
    this.write({
      ...current,
      fullName: normalizedName || current.fullName,
      displayName: normalizedName || current.displayName,
      language: this.normalizeLanguage(profile.preferred_language?.trim()) || current.language,
    });
  }

  private mergePrefs(parsed: Partial<UserProfilePreferences>): UserProfilePreferences {
    return {
      fullName: parsed.fullName?.trim() || DEFAULT_PREFS.fullName,
      displayName: parsed.displayName?.trim() || DEFAULT_PREFS.displayName,
      jobDescription: parsed.jobDescription ?? DEFAULT_PREFS.jobDescription,
      responsePreferences: parsed.responsePreferences ?? DEFAULT_PREFS.responsePreferences,
      language: parsed.language?.trim() || DEFAULT_PREFS.language,
      responseCompletionNotifications:
        typeof parsed.responseCompletionNotifications === 'boolean'
          ? parsed.responseCompletionNotifications
          : DEFAULT_PREFS.responseCompletionNotifications,
      sendMessageNotifications:
        typeof parsed.sendMessageNotifications === 'boolean'
          ? parsed.sendMessageNotifications
          : DEFAULT_PREFS.sendMessageNotifications,
      colorMode:
        parsed.colorMode === 'light' || parsed.colorMode === 'auto' || parsed.colorMode === 'dark'
          ? parsed.colorMode
          : DEFAULT_PREFS.colorMode,
      backgroundAnimation:
        parsed.backgroundAnimation === 'on' || parsed.backgroundAnimation === 'auto' || parsed.backgroundAnimation === 'off'
          ? parsed.backgroundAnimation
          : DEFAULT_PREFS.backgroundAnimation,
      chatFont:
        parsed.chatFont === 'default' ||
        parsed.chatFont === 'sans' ||
        parsed.chatFont === 'system' ||
        parsed.chatFont === 'dyslexic'
          ? parsed.chatFont
          : DEFAULT_PREFS.chatFont,
      dataSharingEnabled:
        typeof parsed.dataSharingEnabled === 'boolean' ? parsed.dataSharingEnabled : DEFAULT_PREFS.dataSharingEnabled,
      memoryEnabled: typeof parsed.memoryEnabled === 'boolean' ? parsed.memoryEnabled : DEFAULT_PREFS.memoryEnabled,
      telemetryEnabled: typeof parsed.telemetryEnabled === 'boolean' ? parsed.telemetryEnabled : DEFAULT_PREFS.telemetryEnabled,
      billingPlan:
        parsed.billingPlan === 'free' || parsed.billingPlan === 'team' || parsed.billingPlan === 'enterprise'
          ? parsed.billingPlan
          : DEFAULT_PREFS.billingPlan,
      billingCycle:
        parsed.billingCycle === 'monthly' || parsed.billingCycle === 'yearly' ? parsed.billingCycle : DEFAULT_PREFS.billingCycle,
      invoicesEmail: parsed.invoicesEmail?.trim() ?? DEFAULT_PREFS.invoicesEmail,
      canUseFiles: typeof parsed.canUseFiles === 'boolean' ? parsed.canUseFiles : DEFAULT_PREFS.canUseFiles,
      canUseWebSearch: typeof parsed.canUseWebSearch === 'boolean' ? parsed.canUseWebSearch : DEFAULT_PREFS.canUseWebSearch,
      canUseCodeExecution:
        typeof parsed.canUseCodeExecution === 'boolean' ? parsed.canUseCodeExecution : DEFAULT_PREFS.canUseCodeExecution,
      connectorsGoogleDrive:
        typeof parsed.connectorsGoogleDrive === 'boolean' ? parsed.connectorsGoogleDrive : DEFAULT_PREFS.connectorsGoogleDrive,
      connectorsSlack: typeof parsed.connectorsSlack === 'boolean' ? parsed.connectorsSlack : DEFAULT_PREFS.connectorsSlack,
      connectorsNotion: typeof parsed.connectorsNotion === 'boolean' ? parsed.connectorsNotion : DEFAULT_PREFS.connectorsNotion,
      claudeCodeAutoRun:
        typeof parsed.claudeCodeAutoRun === 'boolean' ? parsed.claudeCodeAutoRun : DEFAULT_PREFS.claudeCodeAutoRun,
      claudeCodeConfirmCommands:
        typeof parsed.claudeCodeConfirmCommands === 'boolean'
          ? parsed.claudeCodeConfirmCommands
          : DEFAULT_PREFS.claudeCodeConfirmCommands,
      avatarVariant:
        typeof parsed.avatarVariant === 'number' && parsed.avatarVariant >= 0
          ? Math.floor(parsed.avatarVariant)
          : DEFAULT_PREFS.avatarVariant,
      responseLength:
        parsed.responseLength === 'short' || parsed.responseLength === 'medium' || parsed.responseLength === 'detailed'
          ? parsed.responseLength
          : DEFAULT_PREFS.responseLength,
      notifyTrackingUpdates:
        typeof parsed.notifyTrackingUpdates === 'boolean' ? parsed.notifyTrackingUpdates : DEFAULT_PREFS.notifyTrackingUpdates,
      notifyAiMentions: typeof parsed.notifyAiMentions === 'boolean' ? parsed.notifyAiMentions : DEFAULT_PREFS.notifyAiMentions,
      notifyExportReady: typeof parsed.notifyExportReady === 'boolean' ? parsed.notifyExportReady : DEFAULT_PREFS.notifyExportReady,
      notifyDeliveryUpdates:
        typeof parsed.notifyDeliveryUpdates === 'boolean' ? parsed.notifyDeliveryUpdates : DEFAULT_PREFS.notifyDeliveryUpdates,
      notifySecurityAlerts:
        typeof parsed.notifySecurityAlerts === 'boolean' ? parsed.notifySecurityAlerts : DEFAULT_PREFS.notifySecurityAlerts,
      dateFormat:
        parsed.dateFormat === 'mdy' || parsed.dateFormat === 'dmy' || parsed.dateFormat === 'ymd'
          ? parsed.dateFormat
          : DEFAULT_PREFS.dateFormat,
      timeFormat: parsed.timeFormat === '12h' || parsed.timeFormat === '24h' ? parsed.timeFormat : DEFAULT_PREFS.timeFormat,
      accentColor:
        parsed.accentColor === 'fedex' ||
        parsed.accentColor === 'purple' ||
        parsed.accentColor === 'orange' ||
        parsed.accentColor === 'blue'
          ? parsed.accentColor
          : DEFAULT_PREFS.accentColor,
      chatDensity:
        parsed.chatDensity === 'compact' || parsed.chatDensity === 'comfortable' || parsed.chatDensity === 'large'
          ? parsed.chatDensity
          : DEFAULT_PREFS.chatDensity,
    };
  }

  private applyToDocument(prefs: UserProfilePreferences): void {
    if (typeof document === 'undefined') {
      return;
    }
    const root = document.documentElement;
    const body = document.body;
    const theme = this.resolveTheme(prefs.colorMode);
    const motion = this.resolveMotion(prefs.backgroundAnimation);
    const palette = ACCENT_PALETTES[prefs.accentColor];

    body.setAttribute('data-color-mode', prefs.colorMode);
    body.setAttribute('data-theme', theme);
    body.setAttribute('data-motion-mode', prefs.backgroundAnimation);
    body.setAttribute('data-motion-effective', motion);
    body.setAttribute('data-chat-font', prefs.chatFont);
    body.setAttribute('data-accent-color', prefs.accentColor);
    body.setAttribute('data-chat-density', prefs.chatDensity);

    const lightTokens = {
      '--bg-page': '#F8F7FC',
      '--bg-card': '#FFFFFF',
      '--text-primary': '#111827',
      '--text-muted': '#64748B',
      '--border-color': '#ECE8F4',
    };
    const darkTokens = {
      '--bg-page': '#1e1f23',
      '--bg-card': '#2a2c31',
      '--text-primary': '#ececec',
      '--text-muted': '#94a3b8',
      '--border-color': '#3b3e45',
    };
    const themeTokens = theme === 'dark' ? darkTokens : lightTokens;

    this.setVars(root, {
      '--color-primary': palette.primary,
      '--color-accent': palette.accent,
      '--color-primary-soft': palette.soft,
      '--radius-card': '24px',
      '--radius-input': '16px',
      '--radius-button': '14px',
      '--ui-accent': palette.primary,
      '--ui-accent-secondary': palette.accent,
      '--fedex-purple': palette.primary,
      '--fedex-purple-soft': palette.soft,
      '--fedex-orange': palette.accent,
      ...themeTokens,
    });

    this.setVars(root, DENSITY_TOKENS[prefs.chatDensity]);

    const chatFontFamily = this.chatFontFamily(prefs.chatFont);
    root.style.setProperty('--chat-font-family', chatFontFamily);
  }

  private setVars(el: HTMLElement, vars: Record<string, string>): void {
    for (const [key, value] of Object.entries(vars)) {
      el.style.setProperty(key, value);
    }
  }

  private resolveTheme(mode: UserProfilePreferences['colorMode']): 'light' | 'dark' {
    if (mode === 'light') {
      return 'light';
    }
    if (mode === 'dark') {
      return 'dark';
    }
    if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  private resolveMotion(mode: UserProfilePreferences['backgroundAnimation']): 'on' | 'off' {
    if (mode === 'off') {
      return 'off';
    }
    if (mode === 'on') {
      return 'on';
    }
    if (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return 'off';
    }
    return 'on';
  }

  private chatFontFamily(font: UserProfilePreferences['chatFont']): string {
    switch (font) {
      case 'sans':
        return 'Inter, Arial, sans-serif';
      case 'system':
        return 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
      case 'dyslexic':
        return 'Arial, "Comic Sans MS", sans-serif';
      default:
        return 'var(--font-sans)';
    }
  }

  private bindSystemListeners(): void {
    if (typeof window === 'undefined') {
      return;
    }
    this.systemThemeMq = window.matchMedia('(prefers-color-scheme: dark)');
    this.reducedMotionMq = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.boundThemeChange = () => {
      this.zone.run(() => this.applyToDocument(this.read()));
    };
    this.boundMotionChange = () => {
      this.zone.run(() => this.applyToDocument(this.read()));
    };
    this.systemThemeMq.addEventListener('change', this.boundThemeChange);
    this.reducedMotionMq.addEventListener('change', this.boundMotionChange);
  }

  private normalizeLanguage(value?: string): string {
    if (!value) {
      return '';
    }
    const normalized = value.toLowerCase();
    if (normalized === 'fr' || normalized === 'français' || normalized === 'french') return 'Français';
    if (normalized === 'en' || normalized === 'english') return 'English';
    if (normalized === 'ar' || normalized === 'arabic') return 'Arabic';
    return '';
  }
}
