import { CommonModule } from '@angular/common';
import { Component, EventEmitter, HostListener, Input, OnInit, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { LangCode } from '../../../core/i18n/i18n.types';
import { I18nService } from '../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../core/i18n/translate.pipe';
import { AuthService } from '../../../core/services/auth.service';
import { EmployeePortalService, EmployeeSettings } from '../../../core/services/employee-portal.service';
import { UserPreferencesService } from '../../../core/services/user-preferences.service';

type SettingsTab = 'profile' | 'security' | 'appearance' | 'language';
type NavIcon = 'user' | 'shield' | 'palette' | 'languages';

interface SettingsNavItem {
  tab: SettingsTab;
  labelKey: string;
  icon: NavIcon;
}

@Component({
  selector: 'app-employee-settings-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe],
  templateUrl: './employee-settings-panel.component.html',
  styleUrls: [
    './employee-settings-panel.component.scss',
    '../../settings/settings-page.component.scss',
  ],
})
export class EmployeeSettingsPanelComponent implements OnInit {
  @Input() tab: SettingsTab = 'profile';
  @Output() closed = new EventEmitter<void>();

  readonly primaryNav: SettingsNavItem[] = [
    { tab: 'profile', labelKey: 'settings.profile', icon: 'user' },
    { tab: 'security', labelKey: 'settings.nav.security', icon: 'shield' },
    { tab: 'appearance', labelKey: 'settings.appearance', icon: 'palette' },
    { tab: 'language', labelKey: 'settings.language', icon: 'languages' },
  ];

  saved = false;
  settings: EmployeeSettings | null = null;
  fullName = '';
  userEmail = '';
  userRole = 'employe';
  avatarInitial = 'E';
  colorMode: 'light' | 'dark' | 'auto' = 'light';
  accentColor: 'fedex' | 'purple' | 'orange' | 'blue' = 'fedex';

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly auth: AuthService,
    readonly i18n: I18nService,
    private readonly userPreferences: UserPreferencesService,
  ) {}

  ngOnInit(): void {
    const prefs = this.userPreferences.read();
    this.colorMode = prefs.colorMode;
    this.accentColor = prefs.accentColor;

    this.auth.me().subscribe({
      next: (p) => {
        this.userEmail = p.email;
        this.avatarInitial = this.initials(p.full_name);
      },
    });

    this.employee.getSettings().subscribe({
      next: (s) => {
        this.settings = s;
        this.fullName = s.full_name;
      },
    });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.close();
  }

  goTo(tab: SettingsTab): void {
    this.tab = tab;
  }

  close(): void {
    this.closed.emit();
  }

  saveProfile(): void {
    this.employee.updateSettings({ full_name: this.fullName, preferred_language: this.i18n.langCode() }).subscribe({
      next: (s) => {
        this.settings = s;
        this.fullName = s.full_name;
        this.showSaved();
      },
    });
  }

  setLanguage(code: LangCode): void {
    this.i18n.setLang(code);
    this.employee.updateSettings({ preferred_language: code }).subscribe({
      next: (s) => {
        this.settings = s;
        this.showSaved();
      },
    });
  }

  setColorMode(mode: 'light' | 'dark' | 'auto'): void {
    this.colorMode = mode;
    const prefs = this.userPreferences.read();
    this.userPreferences.write({ ...prefs, colorMode: mode });
    this.showSaved();
  }

  setAccentColor(color: 'fedex' | 'purple' | 'orange' | 'blue'): void {
    this.accentColor = color;
    const prefs = this.userPreferences.read();
    this.userPreferences.write({ ...prefs, accentColor: color });
    this.showSaved();
  }

  private showSaved(): void {
    this.saved = true;
    setTimeout(() => (this.saved = false), 2000);
  }

  private initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'E';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  accountNameFallback(): string {
    return this.fullName || this.settings?.full_name || 'Employé';
  }
}
