import { Injectable } from '@angular/core';
import { Router } from '@angular/router';

import { ChatSessionService, ChatSessionSummary } from './chat-session.service';

export type ConversationSidebarAction = 'rename' | 'move' | 'delete';

@Injectable({ providedIn: 'root' })
export class ConversationSidebarBridgeService {
  constructor(
    private readonly router: Router,
    private readonly chatSessions: ChatSessionService,
  ) {}

  openChat(sessionId?: string): void {
    if (sessionId?.trim()) {
      void this.router.navigate(['/chat'], { queryParams: { session: sessionId.trim() } });
      return;
    }
    void this.router.navigateByUrl('/chat');
  }

  navigateAction(sessionId: string, action: ConversationSidebarAction): void {
    const cleaned = sessionId.trim();
    if (!cleaned) {
      return;
    }
    void this.router.navigate(['/chat'], { queryParams: { session: cleaned, action } });
  }

  togglePin(
    sessions: ChatSessionSummary[],
    sessionId: string,
    onUpdated: () => void,
    onError?: () => void,
  ): void {
    const id = Number(sessionId);
    if (!Number.isFinite(id) || id <= 0) {
      return;
    }
    const session = sessions.find((row) => row.id === id);
    if (!session) {
      return;
    }
    this.chatSessions.update(id, { is_pinned: !session.is_pinned }).subscribe({
      next: () => onUpdated(),
      error: () => onError?.(),
    });
  }
}
