import { CommonModule } from '@angular/common';
import {
  AfterViewChecked,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  ViewChild,
  inject,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { I18nService } from '../../../../core/i18n/i18n.service';
import { ChatFormattedTextPipe } from '../../../../shared/pipes/chat-formatted-text.pipe';
import { ShipmentCardComponent } from '../../../../shared/components/shipment-card/shipment-card.component';
import { shouldShowShipmentCardInChat } from '../../../../shared/utils/shipment-card.util';
import { ExportDownloadSpec } from '../../../../core/services/chatbot.service';
import { HistoryService } from '../../../../core/services/history.service';
import { AgentQuestionnaire, AgentSuggestion } from '../../../../core/models/chat-send.model';
import { UiMessage } from '../message-list/message-list.component';
import { FedexAiAvatarComponent } from './fedex-ai-avatar.component';
import { AgentQuestionnaireComponent } from '../agent-questionnaire/agent-questionnaire.component';

@Component({
  selector: 'app-conversation-messages',
  standalone: true,
  imports: [CommonModule, ShipmentCardComponent, TranslatePipe, FedexAiAvatarComponent, ChatFormattedTextPipe, AgentQuestionnaireComponent],
  templateUrl: './conversation-messages.component.html',
  styleUrl: './conversation-messages.component.scss',
})
export class ConversationMessagesComponent implements AfterViewChecked, OnChanges {
  private readonly router = inject(Router);
  private readonly history = inject(HistoryService);
  private readonly i18n = inject(I18nService);

  readonly exportLoadingId = signal<number | null>(null);

  @Input({ required: true }) messages: UiMessage[] = [];
  @Input() thinking = false;
  @Input() userInitial = '?';
  @Input() inputDisabled = false;

  @Output() agentAnswers = new EventEmitter<{ flowId: string; answers: Record<string, string> }>();
  @Output() agentSuggestionActivate = new EventEmitter<AgentSuggestion>();

  @ViewChild('scrollRoot') scrollRoot?: ElementRef<HTMLElement>;

  private shouldScroll = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['messages'] || changes['thinking']) {
      this.shouldScroll = true;
    }
  }

  ngAfterViewChecked(): void {
    if (!this.shouldScroll) {
      return;
    }
    const el = this.scrollRoot?.nativeElement;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
    this.shouldScroll = false;
  }

  sourceLabel(source: UiMessage['source']): string {
    // Un seul assistant visible — pas de badges techniques (LLM/Ollama/FedEx API).
    return '';
  }

  hasTrackingResponse(m: UiMessage): boolean {
    return m.role === 'bot' && !!this.trackingNumber(m);
  }

  showShipmentCard(shipment: UiMessage['shipment']): boolean {
    return shouldShowShipmentCardInChat(shipment);
  }

  trackingNumber(m: UiMessage): string | null {
    const fromResponse = m.trackingNumber?.trim();
    if (fromResponse) {
      return fromResponse;
    }
    const fromCard = m.shipment?.tracking_number?.trim();
    if (fromCard) {
      return fromCard;
    }
    const match = m.text.match(/\b(\d{10,15})\b/);
    return match?.[1] ?? null;
  }

  openTrackingHistory(m: UiMessage, event: Event): void {
    event.stopPropagation();
    const tracking = this.trackingNumber(m);
    void this.router.navigate(['/history'], {
      queryParams: tracking ? { tracking } : {},
    });
  }

  onAgentSubmit(flowId: string, answers: Record<string, string>): void {
    this.agentAnswers.emit({ flowId, answers });
  }

  onActivateAgentSuggestion(suggestion: AgentSuggestion): void {
    this.agentSuggestionActivate.emit(suggestion);
  }

  exportLead(spec: ExportDownloadSpec, messageText?: string | null): string {
    const hasExplanation = Boolean((messageText || '').trim().length > 40);
    if (hasExplanation) {
      return this.i18n.t('conversation.exportDownloadHint');
    }
    return this.history.isPdfExport(spec)
      ? this.i18n.t('conversation.exportHerePdf')
      : this.i18n.t('conversation.exportHereExcel');
  }

  exportLinkLabel(spec: ExportDownloadSpec): string {
    const file = this.history.exportFilename(spec);
    return this.i18n.t('conversation.exportDownloadLink', { file });
  }

  downloadExport(messageId: number, spec: ExportDownloadSpec): void {
    if (this.exportLoadingId() === messageId) {
      return;
    }
    this.exportLoadingId.set(messageId);
    const lang = this.i18n.toBackendCode() as 'fr' | 'en' | 'ar';
    this.history.downloadFromSpec(spec, lang).subscribe({
      next: () => this.exportLoadingId.set(null),
      error: () => this.exportLoadingId.set(null),
    });
  }
}
