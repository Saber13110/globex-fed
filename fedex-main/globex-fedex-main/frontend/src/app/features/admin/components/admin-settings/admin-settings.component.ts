import { animate, style, transition, trigger } from '@angular/animations';
import { CommonModule, DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, OnInit, Output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { AdminDashboardStats, AdminService, AdminUser } from '../../../../core/services/admin.service';
import {
  AiSettings,
  IntegrationSettings,
  NotificationSettings,
  SecuritySettings,
  ServiceHealthItem,
  SystemHealthResponse,
  SystemInfoResponse,
  SystemSettingsPayload,
  SystemSettingsService,
} from '../../../../core/services/system-settings.service';

type SettingsTab = 'general' | 'security' | 'notifications' | 'integrations' | 'ai' | 'about';

@Component({
  selector: 'app-admin-settings',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, MatSnackBarModule],
  templateUrl: './admin-settings.component.html',
  styleUrl: './admin-settings.component.scss',
  animations: [
    trigger('fadeIn', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(6px)' }),
        animate('220ms ease-out', style({ opacity: 1, transform: 'translateY(0)' })),
      ]),
    ]),
  ],
})
export class AdminSettingsComponent implements OnInit {
  @Input() defaultTestEmail = '';
  @Output() navigateAudit = new EventEmitter<void>();

  readonly tabs: { id: SettingsTab; label: string; icon: string }[] = [
    { id: 'general', label: 'Général', icon: 'general' },
    { id: 'security', label: 'Sécurité', icon: 'security' },
    { id: 'notifications', label: 'Notifications', icon: 'notifications' },
    { id: 'integrations', label: 'Intégrations', icon: 'integrations' },
    { id: 'ai', label: 'IA & Automatisation', icon: 'ai' },
    { id: 'about', label: 'À propos', icon: 'about' },
  ];

  readonly activeTab = signal<SettingsTab>('general');
  readonly saving = signal(false);
  readonly loading = signal(true);
  readonly statsLoading = signal(true);
  readonly healthLoading = signal(true);
  readonly opLoading = signal<string | null>(null);

  readonly stats = signal<AdminDashboardStats | null>(null);
  readonly health = signal<SystemHealthResponse | null>(null);
  readonly systemInfo = signal<SystemInfoResponse | null>(null);
  readonly pending = signal<AdminUser[]>([]);
  readonly pendingBusyId = signal<number | null>(null);

  notifications: NotificationSettings = {
    email: true,
    sms: false,
    in_app: true,
    critical_alerts: true,
  };
  security: SecuritySettings = { mfa_enabled: true };
  integrations: IntegrationSettings = {
    smtp: { host: '', port: 587, user: '', use_tls: true, password_set: false },
  };
  ai: AiSettings = {
    provider: 'gemini',
    temperature: 0.7,
    max_tokens: 2048,
    system_prompt: '',
  };

  testEmailTo = '';
  pwdCurrent = '';
  pwdNew = '';
  pwdConfirm = '';

  constructor(
    private readonly api: SystemSettingsService,
    private readonly admin: AdminService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.testEmailTo = this.defaultTestEmail;
    this.reloadAll();
  }

  setTab(tab: SettingsTab): void {
    this.activeTab.set(tab);
  }

  reloadAll(): void {
    this.loading.set(true);
    this.statsLoading.set(true);
    this.healthLoading.set(true);

    this.api.getSettings().subscribe({
      next: (s) => this.applySettings(s),
      error: () => this.toast('Impossible de charger les paramètres.', 'error'),
    });

    this.api.getDashboardStats().subscribe({
      next: (s) => {
        this.stats.set(s);
        this.statsLoading.set(false);
      },
      error: () => {
        this.statsLoading.set(false);
        this.toast('Statistiques indisponibles.', 'error');
      },
    });

    this.api.getHealth().subscribe({
      next: (h) => {
        this.health.set(h);
        this.healthLoading.set(false);
      },
      error: () => {
        this.healthLoading.set(false);
        this.toast('État des services indisponible.', 'error');
      },
    });

    this.api.getSystemInfo().subscribe({
      next: (i) => this.systemInfo.set(i),
      error: () => {},
    });

    this.admin.listPendingEmployees().subscribe({
      next: (rows) => this.pending.set(rows),
      error: () => this.pending.set([]),
    });

    this.loading.set(false);
  }

  validateEmployee(user: AdminUser): void {
    this.pendingBusyId.set(user.id);
    this.admin.validateEmployee(user.id).subscribe({
      next: () => {
        this.pendingBusyId.set(null);
        this.toast(`Employé ${user.email} validé.`, 'success');
        this.reloadAll();
      },
      error: (err: HttpErrorResponse) => {
        this.pendingBusyId.set(null);
        this.toast(this.errorDetail(err, 'Validation échouée.'), 'error');
      },
    });
  }

  rejectEmployee(user: AdminUser): void {
    if (!confirm(`Rejeter la demande de ${user.full_name} ?`)) return;
    this.pendingBusyId.set(user.id);
    this.admin.rejectEmployee(user.id).subscribe({
      next: () => {
        this.pendingBusyId.set(null);
        this.toast(`Demande de ${user.email} rejetée.`, 'success');
        this.reloadAll();
      },
      error: (err: HttpErrorResponse) => {
        this.pendingBusyId.set(null);
        this.toast(this.errorDetail(err, 'Rejet échoué.'), 'error');
      },
    });
  }

  refreshHealth(): void {
    this.healthLoading.set(true);
    this.api.getHealth().subscribe({
      next: (h) => {
        this.health.set(h);
        this.healthLoading.set(false);
      },
      error: () => {
        this.healthLoading.set(false);
        this.toast('Actualisation impossible.', 'error');
      },
    });
  }

  save(): void {
    this.saving.set(true);
    const tab = this.activeTab();
    const patch =
      tab === 'notifications'
        ? { notifications: { ...this.notifications } }
        : tab === 'security'
          ? { security: { ...this.security } }
          : tab === 'integrations'
            ? { integrations: { ...this.integrations, smtp: { ...this.integrations.smtp } } }
            : tab === 'ai'
              ? { ai: { ...this.ai } }
              : {
                  notifications: { ...this.notifications },
                  security: { ...this.security },
                  integrations: { ...this.integrations, smtp: { ...this.integrations.smtp } },
                  ai: { ...this.ai },
                };

    this.api.patchSettings(patch).subscribe({
      next: (s) => {
        this.applySettings(s);
        this.saving.set(false);
        this.toast('Modifications enregistrées.', 'success');
        this.refreshHealth();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.toast(this.errorDetail(err, 'Échec de la sauvegarde.'), 'error');
      },
    });
  }

  sendTestEmail(): void {
    const to = this.testEmailTo.trim();
    if (!to || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
      this.toast('Adresse email invalide.', 'error');
      return;
    }
    this.opLoading.set('email');
    this.api.testEmail(to).subscribe({
      next: () => {
        this.opLoading.set(null);
        this.toast('Email envoyé avec succès.', 'success');
      },
      error: (err: HttpErrorResponse) => {
        this.opLoading.set(null);
        this.toast(this.errorDetail(err, "Échec de l'envoi."), 'error');
      },
    });
  }

  changePassword(): void {
    if (!this.pwdCurrent || !this.pwdNew || !this.pwdConfirm) {
      this.toast('Tous les champs sont obligatoires.', 'error');
      return;
    }
    if (this.pwdNew.length < 8) {
      this.toast('Le nouveau mot de passe doit contenir au moins 8 caractères.', 'error');
      return;
    }
    if (this.pwdNew !== this.pwdConfirm) {
      this.toast('Les mots de passe ne correspondent pas.', 'error');
      return;
    }
    this.opLoading.set('password');
    this.api.changePassword(this.pwdCurrent, this.pwdNew, this.pwdConfirm).subscribe({
      next: () => {
        this.opLoading.set(null);
        this.pwdCurrent = '';
        this.pwdNew = '';
        this.pwdConfirm = '';
        this.toast('Mot de passe mis à jour.', 'success');
      },
      error: (err: HttpErrorResponse) => {
        this.opLoading.set(null);
        this.toast(this.errorDetail(err, 'Échec du changement de mot de passe.'), 'error');
      },
    });
  }

  runOp(kind: 'cache' | 'reindex' | 'backup'): void {
    const labels = { cache: 'cache', reindex: 'réindexation', backup: 'sauvegarde' };
    if (!confirm(`Confirmer l'opération : ${labels[kind]} ?`)) return;
    this.opLoading.set(kind);
    const req =
      kind === 'cache' ? this.api.clearCache() : kind === 'reindex' ? this.api.reindex() : this.api.backup();
    req.subscribe({
      next: (r) => {
        this.opLoading.set(null);
        this.toast(r.message, r.ok ? 'success' : 'error');
      },
      error: (err: HttpErrorResponse) => {
        this.opLoading.set(null);
        this.toast(this.errorDetail(err, 'Opération échouée.'), 'error');
      },
    });
  }

  testIntegration(provider: 'fedex' | 'gemini' | 'openai'): void {
    this.opLoading.set(provider);
    const req =
      provider === 'fedex'
        ? this.api.testFedex()
        : provider === 'gemini'
          ? this.api.testGemini()
          : this.api.testOpenai();
    req.subscribe({
      next: (r) => {
        this.opLoading.set(null);
        this.toast(r.message, r.ok ? 'success' : 'error');
        this.refreshHealth();
      },
      error: (err: HttpErrorResponse) => {
        this.opLoading.set(null);
        this.toast(this.errorDetail(err, 'Test échoué.'), 'error');
      },
    });
  }

  serviceStatusLabel(s: ServiceHealthItem): string {
    const map: Record<string, string> = {
      online: 'Actif',
      offline: 'Hors ligne',
      degraded: 'Dégradé',
      disabled: 'Désactivé',
      not_configured: 'Non configuré',
    };
    return map[s.status] ?? s.status;
  }

  fedexConnected(): boolean {
    return this.health()?.services.find((x) => x.key === 'fedex')?.status === 'online';
  }

  aiModelLabel(): string {
    const p = this.ai.provider;
    if (p === 'gemini') return 'Gemini';
    if (p === 'openai') return 'OpenAI';
    if (p === 'claude') return 'Claude';
    return 'LLM local (Ollama)';
  }

  private applySettings(s: SystemSettingsPayload): void {
    this.notifications = { ...s.notifications };
    this.security = { ...s.security };
    this.integrations = {
      smtp: { ...s.integrations.smtp },
    };
    this.ai = { ...s.ai };
  }

  private toast(message: string, type: 'success' | 'error'): void {
    this.snack.open(message, 'Fermer', {
      duration: 4200,
      panelClass: type === 'success' ? 'set-snack--ok' : 'set-snack--err',
      horizontalPosition: 'end',
      verticalPosition: 'top',
    });
  }

  private errorDetail(err: HttpErrorResponse, fallback: string): string {
    const d = err.error?.detail;
    return typeof d === 'string' ? d : fallback;
  }
}
