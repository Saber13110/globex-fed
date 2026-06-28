import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subscription } from 'rxjs';

import { AuthService } from './auth.service';
import { ChatSessionService, ChatSessionSummary } from './chat-session.service';

@Injectable({ providedIn: 'root' })
export class SidebarSessionsService implements OnDestroy {
  private readonly sessionsSubject = new BehaviorSubject<ChatSessionSummary[]>([]);
  private readonly loadingSubject = new BehaviorSubject<boolean>(false);
  private lastFetchMs = 0;
  private inFlight: Subscription | null = null;

  /** Durée de validité du cache — évite un rechargement à chaque changement de page. */
  private readonly cacheTtlMs = 45_000;

  readonly sessions$ = this.sessionsSubject.asObservable();
  readonly loading$ = this.loadingSubject.asObservable();

  constructor(
    private readonly chatSessions: ChatSessionService,
    private readonly auth: AuthService,
  ) {}

  ngOnDestroy(): void {
    this.inFlight?.unsubscribe();
  }

  get snapshot(): ChatSessionSummary[] {
    return this.sessionsSubject.value;
  }

  get loading(): boolean {
    return this.loadingSubject.value;
  }

  ensureLoaded(force = false): void {
    if (!this.auth.token()) {
      return;
    }

    const now = Date.now();
    const hasCache = this.sessionsSubject.value.length > 0;
    if (!force && hasCache && now - this.lastFetchMs < this.cacheTtlMs) {
      return;
    }
    if (this.inFlight) {
      return;
    }

    this.loadingSubject.next(true);
    this.inFlight = this.chatSessions.list({ limit: 80, include_archived: true }).subscribe({
      next: (rows) => {
        this.sessionsSubject.next(rows);
        this.lastFetchMs = Date.now();
        this.loadingSubject.next(false);
        this.inFlight = null;
      },
      error: () => {
        this.loadingSubject.next(false);
        this.inFlight = null;
      },
    });
  }

  invalidate(): void {
    this.lastFetchMs = 0;
  }

  refresh(): void {
    this.ensureLoaded(true);
  }

  /** Met à jour le cache après une mutation (ex. page chat). */
  publish(rows: ChatSessionSummary[]): void {
    this.sessionsSubject.next(rows);
    this.lastFetchMs = Date.now();
  }
}
