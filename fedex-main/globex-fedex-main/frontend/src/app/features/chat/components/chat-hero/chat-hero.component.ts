import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { ChatSendPayload } from '../../../../core/models/chat-send.model';
import { ChatInputComponent } from '../chat-input/chat-input.component';

export interface HeroStat {
  id: string;
  value: string;
  label: string;
  tone: 'purple' | 'green' | 'orange';
  icon: 'box' | 'doc' | 'shield';
  operational?: boolean;
}

export interface HeroAction {
  id: string;
  title: string;
  subtitle: string;
  text: string;
  icon: 'track' | 'excel' | 'issue' | 'proof';
}

@Component({
  selector: 'app-chat-hero',
  standalone: true,
  imports: [CommonModule, ChatInputComponent, TranslatePipe],
  templateUrl: './chat-hero.component.html',
  styleUrl: './chat-hero.component.scss',
})
export class ChatHeroComponent {
  @Input() displayName = '';
  @Input() greetingPrefix = 'Bonjour';
  @Input() folderName: string | null = null;
  @Input() actions: HeroAction[] = [];
  @Input() stats: HeroStat[] = [];
  @Input() inputDisabled = false;

  @Output() send = new EventEmitter<ChatSendPayload>();
  @Output() actionSelect = new EventEmitter<HeroAction>();
}
