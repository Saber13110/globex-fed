import { CommonModule, DatePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';

import {
  AGENT_OPTIONS,
  AgentMissionListItem,
  AgentMissionsService,
  MissionStatus,
} from '../../../../../core/services/agent-missions.service';

@Component({
  selector: 'app-agent-missions-list',
  standalone: true,
  imports: [CommonModule, DatePipe, RouterLink],
  templateUrl: './agent-missions-list.component.html',
  styleUrl: './agent-missions-list.component.scss',
})
export class AgentMissionsListComponent implements OnInit {
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly items = signal<AgentMissionListItem[]>([]);
  readonly stats = signal({ total: 0, waiting_plan_approval: 0, running: 0, completed: 0 });
  readonly busyId = signal<number | null>(null);

  readonly agentOptions = AGENT_OPTIONS;

  constructor(private readonly api: AgentMissionsService) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.list().subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.stats.set(res.stats);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Impossible de charger les missions.');
        this.loading.set(false);
      },
    });
  }

  agentLabel(type: string): string {
    return this.agentOptions.find((a) => a.value === type)?.label || type;
  }

  statusLabel(status: MissionStatus): string {
    const map: Record<MissionStatus, string> = {
      draft: 'Prête',
      waiting_plan_approval: 'Prête',
      scheduled: 'Planifiée',
      running: 'En cours',
      waiting_permission: 'Permission requise',
      completed: 'Terminée',
      failed: 'Échouée',
      cancelled: 'Annulée',
    };
    return map[status] || status;
  }

  scheduleLabel(item: AgentMissionListItem): string {
    if (item.schedule_type === 'now') return 'Immédiate';
    if (item.schedule_type === 'datetime' && item.scheduled_at) {
      return new Date(item.scheduled_at).toLocaleString('fr-FR');
    }
    if (item.schedule_type === 'daily') return 'Quotidienne';
    if (item.schedule_type === 'weekly') return 'Hebdomadaire';
    return item.schedule_type;
  }

  canEdit(item: AgentMissionListItem): boolean {
    return ['draft', 'failed', 'waiting_plan_approval', 'scheduled'].includes(item.status);
  }

  canRun(item: AgentMissionListItem): boolean {
    return ['draft', 'scheduled', 'waiting_permission', 'failed', 'waiting_plan_approval'].includes(item.status);
  }

  canCancel(item: AgentMissionListItem): boolean {
    return !['completed', 'cancelled', 'failed'].includes(item.status);
  }

  runMission(id: number, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    this.busyId.set(id);
    this.api.run(id).subscribe({
      next: () => this.refresh(),
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Exécution impossible.');
        this.busyId.set(null);
      },
      complete: () => this.busyId.set(null),
    });
  }

  cancelMission(id: number, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    if (!confirm('Annuler cette mission ?')) return;
    this.busyId.set(id);
    this.api.cancel(id).subscribe({
      next: () => this.refresh(),
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Annulation impossible.');
        this.busyId.set(null);
      },
      complete: () => this.busyId.set(null),
    });
  }
}
