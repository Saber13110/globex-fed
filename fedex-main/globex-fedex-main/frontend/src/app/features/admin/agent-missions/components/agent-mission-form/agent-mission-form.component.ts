import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';

import {
  AGENT_OPTIONS,
  AgentMissionsService,
  AgentType,
  SCHEDULE_OPTIONS,
  ScheduleType,
} from '../../../../../core/services/agent-missions.service';

@Component({
  selector: 'app-agent-mission-form',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './agent-mission-form.component.html',
  styleUrl: './agent-mission-form.component.scss',
})
export class AgentMissionFormComponent {
  readonly agentOptions = AGENT_OPTIONS;
  readonly scheduleOptions = SCHEDULE_OPTIONS;
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  agentType: AgentType = 'support';
  taskDescription = '';
  scheduleType: ScheduleType = 'now';
  scheduledAt = '';
  scheduleTime = '08:00';
  maxItems = 10;
  maxDurationMinutes = 15;
  requireApprovalSensitive = true;
  notifyOnStart = true;
  notifyOnComplete = true;

  constructor(
    private readonly api: AgentMissionsService,
    private readonly router: Router,
  ) {}

  get showDatetime(): boolean {
    return this.scheduleType === 'datetime';
  }

  get showScheduleTime(): boolean {
    return this.scheduleType === 'daily' || this.scheduleType === 'weekly';
  }

  private buildPayload() {
    let scheduled_at: string | null = null;
    if (this.scheduleType === 'datetime' && this.scheduledAt) {
      scheduled_at = new Date(this.scheduledAt).toISOString();
    }
    return {
      agent_type: this.agentType,
      task_description: this.taskDescription.trim(),
      schedule_type: this.scheduleType,
      scheduled_at,
      schedule_time: this.scheduleTime,
      max_items: this.maxItems,
      max_duration_minutes: this.maxDurationMinutes,
      require_approval_sensitive: this.requireApprovalSensitive,
      notify_on_start: this.notifyOnStart,
      notify_on_complete: this.notifyOnComplete,
    };
  }

  private validate(): boolean {
    if (this.taskDescription.trim().length < 10) {
      this.error.set('La tâche doit contenir au moins 10 caractères.');
      return false;
    }
    return true;
  }

  save(andRun = false): void {
    if (!this.validate()) return;
    this.saving.set(true);
    this.error.set(null);
    this.api.create(this.buildPayload()).subscribe({
      next: (mission) => {
        if (andRun && this.scheduleType === 'now') {
          this.api.run(mission.id).subscribe({
            next: () => this.router.navigate(['/admin/agent-missions', mission.id], { queryParams: { tab: 'results' } }),
            error: (err: HttpErrorResponse) => {
              this.error.set(err.error?.detail || 'Lancement impossible.');
              this.router.navigate(['/admin/agent-missions', mission.id]);
            },
          });
        } else {
          this.router.navigate(['/admin/agent-missions', mission.id]);
        }
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.detail || 'Enregistrement impossible.');
        this.saving.set(false);
      },
    });
  }

  createAndRun(): void {
    this.save(true);
  }
}
