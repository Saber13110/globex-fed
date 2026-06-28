import { Injectable, computed, signal } from '@angular/core';

import { UserPreferencesService } from '../services/user-preferences.service';
import { LangCode } from './i18n.types';
import { LANGUAGE_OPTIONS, TRANSLATIONS } from './translations';

@Injectable({ providedIn: 'root' })
export class I18nService {
  private readonly _lang = signal<LangCode>(this.readInitialLang());

  readonly lang = this._lang.asReadonly();
  readonly isRtl = computed(() => this._lang() === 'ar');
  readonly languageOptions = LANGUAGE_OPTIONS;

  constructor(private readonly prefs: UserPreferencesService) {
    this.applyToDocument(this._lang());
  }

  t(key: string, params?: Record<string, string>): string {
    const lang = this._lang();
    let value = TRANSLATIONS[lang][key] ?? TRANSLATIONS.fr[key] ?? key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        value = value.replaceAll(`{{${k}}}`, v);
      }
    }
    return value;
  }

  /** Alias for templates and components. */
  translate(key: string, params?: Record<string, string>): string {
    return this.t(key, params);
  }

  langCode(): LangCode {
    return this._lang();
  }

  /** Display label used by chat backend (Français / English / Arabic). */
  uiLanguageLabel(): string {
    return this.toDisplayName(this._lang());
  }

  setLang(code: LangCode, persist = true): void {
    if (this._lang() === code) {
      return;
    }
    this._lang.set(code);
    this.applyToDocument(code);
    if (persist) {
      const current = this.prefs.read();
      this.prefs.write({ ...current, language: this.toDisplayName(code) });
    }
  }

  setFromDisplayName(displayName: string, persist = true): void {
    this.setLang(this.displayNameToCode(displayName), persist);
  }

  syncFromAuthProfile(preferredLanguage?: string | null): void {
    const fromProfile = this.normalizeCode(preferredLanguage);
    if (!fromProfile) {
      return;
    }
    this.setLang(fromProfile, true);
  }

  toBackendCode(code?: LangCode): string {
    return code ?? this._lang();
  }

  toDisplayName(code: LangCode): string {
    return LANGUAGE_OPTIONS.find((o) => o.code === code)?.label ?? 'Français';
  }

  displayNameToCode(displayName: string): LangCode {
    const normalized = displayName.trim().toLowerCase();
    if (normalized === 'english' || normalized === 'en') {
      return 'en';
    }
    if (normalized === 'arabic' || normalized === 'ar') {
      return 'ar';
    }
    return 'fr';
  }

  greetingPrefix(): string {
    const h = new Date().getHours();
    if (h < 12) {
      return this.t('chat.greeting.morning');
    }
    if (h < 18) {
      return this.t('chat.greeting.afternoon');
    }
    return this.t('chat.greeting.evening');
  }

  languageShort(): string {
    const code = this._lang();
    if (code === 'en') {
      return 'EN';
    }
    if (code === 'ar') {
      return 'AR';
    }
    return 'FR';
  }

  private readInitialLang(): LangCode {
    try {
      return this.displayNameToCode(this.prefs.read().language);
    } catch {
      return 'fr';
    }
  }

  private normalizeCode(value?: string | null): LangCode | null {
    if (!value) {
      return null;
    }
    const v = value.trim().toLowerCase();
    if (v === 'fr' || v === 'français' || v === 'french' || v.startsWith('fr-')) {
      return 'fr';
    }
    if (v === 'en' || v === 'english' || v.startsWith('en-')) {
      return 'en';
    }
    if (v === 'ar' || v === 'arabic' || v.startsWith('ar-')) {
      return 'ar';
    }
    return null;
  }

  private applyToDocument(code: LangCode): void {
    if (typeof document === 'undefined') {
      return;
    }
    document.documentElement.setAttribute('lang', code);
    document.documentElement.setAttribute('dir', code === 'ar' ? 'rtl' : 'ltr');
  }
}
