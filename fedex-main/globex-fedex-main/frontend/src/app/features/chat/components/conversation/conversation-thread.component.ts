import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, inject, signal } from '@angular/core';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { I18nService } from '../../../../core/i18n/i18n.service';
import { ChatSendPayload, AgentSuggestion } from '../../../../core/models/chat-send.model';
import { HistoryService } from '../../../../core/services/history.service';
import { ChatInputComponent } from '../chat-input/chat-input.component';
import { UiMessage } from '../message-list/message-list.component';
import { ConversationHeaderComponent } from './conversation-header.component';
import { ConversationMessagesComponent } from './conversation-messages.component';
import { userInitial } from './conversation.utils';

@Component({
  selector: 'app-conversation-thread',
  standalone: true,
  imports: [
    CommonModule,
    ConversationHeaderComponent,
    ConversationMessagesComponent,
    ChatInputComponent,
    TranslatePipe,
  ],
  templateUrl: './conversation-thread.component.html',
  styleUrl: './conversation-thread.component.scss',
})
export class ConversationThreadComponent {
  private readonly i18n = inject(I18nService);
  private readonly history = inject(HistoryService);

  @Input({ required: true }) title = '';
  @Input() sessionUpdatedAt = '';
  @Input() isPinned = false;
  @Input() userName = '';
  @Input() messages: UiMessage[] = [];
  @Input() loading = false;
  @Input() thinking = false;
  @Input() error: string | null = null;
  @Input() inputDisabled = false;

  @Output() send = new EventEmitter<ChatSendPayload>();
  @Output() shareConversation = new EventEmitter<void>();
  @Output() renameConversation = new EventEmitter<void>();
  @Output() togglePinConversation = new EventEmitter<void>();
  @Output() moveConversation = new EventEmitter<void>();
  @Output() deleteConversation = new EventEmitter<void>();
  @Output() agentAnswers = new EventEmitter<{ flowId: string; answers: Record<string, string> }>();
  @Output() agentSuggestionActivate = new EventEmitter<AgentSuggestion>();

  readonly exportLoading = signal(false);

  avatarInitial(): string {
    return userInitial(this.userName);
  }

  onExport(): void {
    this.exportLoading.set(true);
    const lang = this.i18n.toBackendCode() as 'fr' | 'en' | 'ar';
    this.history.downloadExcel({ lang, limit: 200, includeEvents: true }).subscribe({
      next: () => this.exportLoading.set(false),
      error: () => this.exportLoading.set(false),
    });
  }
}
