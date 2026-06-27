import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

import { EmployeePortalService } from './employee-portal.service';

@Injectable({ providedIn: 'root' })
export class EmployeeNotificationsStateService {
  private readonly unreadSubject = new BehaviorSubject(0);
  private readonly freshSubject = new BehaviorSubject(false);

  readonly unread$ = this.unreadSubject.asObservable();
  readonly freshPulse$ = this.freshSubject.asObservable();

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private freshTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly employee: EmployeePortalService) {}

  startPolling(intervalMs = 12_000): void {
    this.stopPolling();
    this.refreshUnread();
    this.pollTimer = setInterval(() => this.refreshUnread(), intervalMs);
  }

  stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  refreshUnread(): void {
    this.employee.listNotifications().subscribe({
      next: ({ unread_count }) => {
        const prev = this.unreadSubject.value;
        this.unreadSubject.next(unread_count);
        if (unread_count > prev) {
          this.triggerFreshPulse();
        }
      },
      error: () => undefined,
    });
  }

  setUnread(count: number): void {
    this.unreadSubject.next(count);
  }

  private triggerFreshPulse(): void {
    this.freshSubject.next(true);
    if (this.freshTimer !== null) {
      clearTimeout(this.freshTimer);
    }
    this.freshTimer = setTimeout(() => {
      this.freshSubject.next(false);
      this.freshTimer = null;
    }, 4500);
  }
}
