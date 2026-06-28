import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { ChatFormattedTextPipe } from '../../../../shared/pipes/chat-formatted-text.pipe';
import { ShipmentCardComponent } from '../../../../shared/components/shipment-card/shipment-card.component';
import { shouldShowShipmentCardInChat } from '../../../../shared/utils/shipment-card.util';
import { ShipmentSummary, ExportDownloadSpec } from '../../../../core/services/chatbot.service';
import { AgentQuestionnaire, AgentReasoning, AgentStep, AgentSuggestion } from '../../../../core/models/chat-send.model';

export interface UiMessage {
  id: number;
  role: 'user' | 'bot';
  text: string;
  imageUrl?: string;
  fileName?: string;
  isDocument?: boolean;
  source?: 'fedex_api' | 'fedex_api+ollama' | 'gemini' | 'ollama' | 'llm' | 'export' | 'export_prompt' | 'fallback' | 'security' | 'unknown' | 'user_input' | 'agent' | 'agent+gemini';
  shipment?: ShipmentSummary | null;
  trackingNumber?: string | null;
  agentQuestionnaire?: AgentQuestionnaire | null;
  agentSteps?: AgentStep[];
  agentReasoning?: AgentReasoning | null;
  agentPhase?: string | null;
  agentSuggestion?: AgentSuggestion | null;
  exportDownload?: ExportDownloadSpec | null;
}

@Component({
  selector: 'app-message-list',
  standalone: true,
  imports: [CommonModule, ShipmentCardComponent, TranslatePipe, ChatFormattedTextPipe],
  templateUrl: './message-list.component.html',
  styleUrl: './message-list.component.scss',
})
export class MessageListComponent {
  @Input({ required: true }) messages: UiMessage[] = [];
  @Input() thinking = false;

  showShipmentCard = shouldShowShipmentCardInChat;
}
