import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild, computed, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import {
  AgentWindowChatResponse,
  AgentWindowHistoryMessage,
  AgentWindowService,
} from '../../../../core/services/agent-window.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { ChatFormattedTextPipe } from '../../../../shared/pipes/chat-formatted-text.pipe';

interface ChatRow {
  id: number;
  role: 'admin' | 'jarvis' | 'system';
  content: string;
  latencyMs?: number | null;
}

@Component({
  selector: 'app-admin-agent-window',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe, ChatFormattedTextPipe],
  templateUrl: './admin-agent-window.component.html',
  styleUrl: './admin-agent-window.component.scss',
})
export class AdminAgentWindowComponent implements OnInit {
  private readonly api = inject(AgentWindowService);
  private chatId = 0;

  readonly openCopilot = output<string>();

  @ViewChild('threadEl') threadEl?: ElementRef<HTMLElement>;

  readonly prompt = signal('');
  readonly sending = signal(false);
  readonly error = signal<string | null>(null);
  readonly sessionId = signal<string | null>(null);
  readonly messages = signal<ChatRow[]>([]);
  readonly jarvisOnline = signal<boolean | null>(null);
  readonly jarvisEnabled = signal(true);
  readonly jarvisLatency = signal<number | null>(null);
  readonly lastEngine = signal<string | null>(null);

  readonly canSend = computed(() => {
    return !!this.prompt().trim() && !this.sending() && this.jarvisOnline() !== false;
  });

  ngOnInit(): void {
    this.refreshHealth();
  }

  refreshHealth(): void {
    this.api.health().subscribe({
      next: (h) => {
        this.jarvisEnabled.set(h.enabled);
        this.jarvisOnline.set(h.online);
        this.jarvisLatency.set(h.latency_ms ?? null);
      },
      error: () => {
        this.jarvisOnline.set(false);
      },
    });
  }

  send(): void {
    const text = this.prompt().trim();
    if (!text || this.sending()) return;

    this.messages.update((rows) => [
      ...rows,
      { id: ++this.chatId, role: 'admin', content: text },
    ]);
    this.prompt.set('');
    this.sending.set(true);
    this.error.set(null);
    this.scrollThread();

    const history: AgentWindowHistoryMessage[] = this.messages()
      .filter((m) => m.role === 'admin' || m.role === 'jarvis')
      .slice(-10)
      .map((m) => ({
        role: m.role === 'admin' ? 'user' : 'assistant',
        content: m.content,
      }));

    this.api
      .chat({
        message: text,
        session_id: this.sessionId(),
        conversation_history: history,
      })
      .subscribe({
        next: (res) => this.onReply(res),
        error: (err: HttpErrorResponse) => {
          const detail =
            typeof err.error?.detail === 'string'
              ? err.error.detail
              : 'Jarvis indisponible — vérifiez qu\'il tourne sur le port 8010.';
          this.error.set(detail);
          this.sending.set(false);
          this.jarvisOnline.set(false);
        },
      });
  }

  newConversation(): void {
    this.sessionId.set(null);
    this.messages.set([]);
    this.error.set(null);
    this.lastEngine.set(null);
  }

  goToCopilot(hint?: string | null): void {
    this.openCopilot.emit(hint || '');
  }

  onEnter(event: Event): void {
    const ke = event as KeyboardEvent;
    if (ke.shiftKey) return;
    event.preventDefault();
    this.send();
  }

  private onReply(res: AgentWindowChatResponse): void {
    this.sessionId.set(res.session_id);
    this.lastEngine.set(res.engine ?? 'jarvis');
    this.messages.update((rows) => [
      ...rows,
      {
        id: ++this.chatId,
        role: res.redirect_to_copilot ? 'system' : 'jarvis',
        content: res.reply,
        latencyMs: res.latency_ms,
      },
    ]);
    this.sending.set(false);
    this.scrollThread();
  }

  private scrollThread(): void {
    setTimeout(() => {
      const el = this.threadEl?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }
}
