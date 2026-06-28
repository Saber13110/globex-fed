import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';

import { ChatItemComponent, Conversation } from '../chat-item/chat-item.component';

@Component({
  selector: 'app-chat-list',
  standalone: true,
  imports: [CommonModule, ChatItemComponent],
  templateUrl: './chat-list.component.html',
  styleUrl: './chat-list.component.scss',
})
export class ChatListComponent {
  @Input({ required: true }) sectionTitle = '';
  @Input({ required: true }) conversations: Conversation[] = [];
  @Input() emptyMessage = '';
  @Input() hideWhenEmpty = false;

  @Output() selectConversation = new EventEmitter<string>();
  @Output() renameConversation = new EventEmitter<{ id: string; title: string }>();
  @Output() togglePinConversation = new EventEmitter<string>();
  @Output() moveConversation = new EventEmitter<string>();
  @Output() deleteConversation = new EventEmitter<string>();
}
