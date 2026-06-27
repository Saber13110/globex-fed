import { CommonModule, DatePipe } from '@angular/common';
import { Component, OnInit, effect, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import {
  AdminService,
  SecurityAgentResponse,
  SecurityIncident,
  SecurityPolicy,
} from '../../../../core/services/admin.service';
import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AdminUserSuspendActionsComponent } from '../admin-user-suspend-actions/admin-user-suspend-actions.component';

@Component({
  selector: 'app-admin-security',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, TranslatePipe, AdminUserSuspendActionsComponent],
  templateUrl: './admin-security.component.html',
  styleUrl: './admin-security.component.scss',
})
export class AdminSecurityComponent implements OnInit {
  readonly highlightIncidentId = input<number | null>(null);
  readonly loading = signal(true);
  readonly busyId = signal<number | null>(null);
  readonly incidents = signal<SecurityIncident[]>([]);
  readonly openCount = signal(0);
  readonly total = signal(0);
  readonly statusFilter = signal<'open' | 'all' | 'resolved' | 'false_positive'>('open');
  readonly policy = signal<SecurityPolicy | null>(null);
  readonly agentReply = signal<string | null>(null);
  readonly agentActions = signal<string[]>([]);
  readonly agentSending = signal(false);
  readonly error = signal<string | null>(null);

  agentPrompt = '';

  constructor(
    private readonly api: AdminService,
    readonly i18n: I18nService,
  ) {
    effect(() => {
      const id = this.highlightIncidentId();
      const rows = this.incidents();
      if (!id || !rows.length) return;
      queueMicrotask(() => {
        const el = document.getElementById('sec-incident-' + id);
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    });
  }

  ngOnInit(): void {
    if (this.highlightIncidentId()) {
      this.statusFilter.set('all');
    }
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set(null);
    const status = this.statusFilter();
    this.api.listSecurityIncidents(status).subscribe({
      next: (res) => {
        this.incidents.set(res.items);
        this.openCount.set(res.open_count);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Impossible de charger les incidents.');
        this.loading.set(false);
      },
    });
    this.api.getSecurityPolicy().subscribe({
      next: (p) => this.policy.set(p),
      error: () => undefined,
    });
  }

  setStatusFilter(value: 'open' | 'all' | 'resolved' | 'false_positive'): void {
    this.statusFilter.set(value);
    this.refresh();
  }

  toggleAutoMode(): void {
    const p = this.policy();
    if (!p) return;
    this.api.updateSecurityPolicy({ auto_mode_enabled: !p.auto_mode_enabled }).subscribe({
      next: (updated) => {
        this.policy.set(updated);
        this.refresh();
      },
    });
  }

  toggleAiIds(): void {
    const p = this.policy();
    if (!p) return;
    this.api.updateSecurityPolicy({ ai_ids_enabled: !p.ai_ids_enabled }).subscribe({
      next: (updated) => this.policy.set(updated),
    });
  }

  runScan(): void {
    this.api.triggerIdsScan(true).subscribe({
      next: () => this.refresh(),
    });
  }

  suspendFromIncident(inc: SecurityIncident): void {
    if (!inc.user_id) return;
    this.busyId.set(inc.id);
    this.api.suspendUserFromIncident(inc.id).subscribe({
      next: () => {
        this.busyId.set(null);
        this.refresh();
      },
      error: () => this.busyId.set(null),
    });
  }

  resolveIncident(inc: SecurityIncident, status: 'resolved' | 'false_positive' | 'acknowledged'): void {
    this.busyId.set(inc.id);
    this.api.resolveSecurityIncident(inc.id, status).subscribe({
      next: () => {
        this.busyId.set(null);
        this.refresh();
      },
      error: () => this.busyId.set(null),
    });
  }

  reactivateUser(inc: SecurityIncident): void {
    if (!inc.user_id) return;
    this.busyId.set(inc.id);
    this.api.reactivateSecurityUser(inc.user_id).subscribe({
      next: () => {
        this.busyId.set(null);
        this.refresh();
      },
      error: () => this.busyId.set(null),
    });
  }

  sendAgent(): void {
    const msg = this.agentPrompt.trim();
    if (!msg || this.agentSending()) return;
    this.agentSending.set(true);
    this.agentReply.set(null);
    this.api.askSecurityAgent(msg).subscribe({
      next: (res: SecurityAgentResponse) => {
        this.agentReply.set(res.reply);
        this.agentActions.set(res.actions_taken);
        if (res.auto_mode_enabled !== undefined && this.policy()) {
          this.policy.set({ ...this.policy()!, auto_mode_enabled: res.auto_mode_enabled });
        }
        this.agentPrompt = '';
        this.agentSending.set(false);
        if (res.actions_taken.length) this.refresh();
      },
      error: (err: HttpErrorResponse) => {
        this.agentReply.set(err.error?.detail || 'Agent sécurité indisponible.');
        this.agentSending.set(false);
      },
    });
  }

  severityClass(sev: string): string {
    if (sev === 'critical' || sev === 'high') return 'high';
    if (sev === 'medium') return 'medium';
    return 'low';
  }
}
