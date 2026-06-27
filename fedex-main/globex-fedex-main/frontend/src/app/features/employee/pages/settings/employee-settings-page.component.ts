import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { LangCode } from '../../../../core/i18n/i18n.types';
import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AuthService } from '../../../../core/services/auth.service';
import { EmployeePortalService, EmployeeSettings } from '../../../../core/services/employee-portal.service';

type SettingsTab = 'profile' | 'security' | 'appearance' | 'language' | 'notifications' | 'ai';

@Component({
  selector: 'app-employee-settings-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-settings-page.component.html',
  styleUrls: ['../../employee-workspace.scss'],
})
export class EmployeeSettingsPageComponent implements OnInit {
  tab: SettingsTab = 'profile';
  settings: EmployeeSettings | null = null;
  saved = false;
  fullName = '';
  preferredLanguage = 'fr';
  responsePreferences = '';
  darkMode = false;

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly auth: AuthService,
    private readonly i18n: I18nService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    const tab = this.route.snapshot.paramMap.get('tab') as SettingsTab | null;
    if (tab) this.tab = tab;
    this.employee.getSettings().subscribe({
      next: (s) => {
        this.settings = s;
        this.fullName = s.full_name;
        this.preferredLanguage = s.preferred_language;
        this.responsePreferences = s.response_preferences;
      },
    });
  }

  setTab(t: SettingsTab): void {
    this.tab = t;
    if (t === 'profile') {
      void this.router.navigate(['/employee/settings']);
    } else {
      void this.router.navigate(['/employee/settings', t]);
    }
  }

  saveProfile(): void {
    this.employee.updateSettings({ full_name: this.fullName, preferred_language: this.preferredLanguage }).subscribe({
      next: (s) => {
        this.settings = s;
        this.saved = true;
        setTimeout(() => (this.saved = false), 2000);
      },
    });
  }

  saveAiPrefs(): void {
    this.employee.updateSettings({ response_preferences: this.responsePreferences }).subscribe({
      next: (s) => {
        this.settings = s;
        this.saved = true;
      },
    });
  }

  setLanguage(code: LangCode): void {
    this.i18n.setLang(code);
    this.preferredLanguage = code;
    this.saveProfile();
  }

  logout(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/employee/login');
  }
}
