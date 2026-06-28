import { CommonModule } from '@angular/common';
import { Component, ElementRef, EventEmitter, HostListener, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

export interface Conversation {
  id: string;
  title: string;
  updatedAt: string;
  isPinned: boolean;
  isActive?: boolean;
}

@Component({
  selector: 'app-chat-item',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-item.component.html',
  styleUrl: './chat-item.component.scss',
})
export class ChatItemComponent {
  @Input({ required: true }) conversation!: Conversation;

  @Output() selectConversation = new EventEmitter<string>();
  @Output() renameConversation = new EventEmitter<{ id: string; title: string }>();
  @Output() togglePinConversation = new EventEmitter<string>();
  @Output() moveConversation = new EventEmitter<string>();
  @Output() deleteConversation = new EventEmitter<string>();

  menuOpen = false;
  isRenaming = false;
  renameDraft = '';

  constructor(private readonly host: ElementRef<HTMLElement>) {}

  onSelect(): void {
    this.selectConversation.emit(this.conversation.id);
  }

  toggleMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen = !this.menuOpen;
  }

  startRename(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen = false;
    this.isRenaming = true;
    this.renameDraft = this.conversation.title;
  }

  saveRename(event?: Event): void {
    event?.stopPropagation();
    const cleaned = this.renameDraft.trim();
    if (!cleaned) {
      return;
    }
    this.renameConversation.emit({ id: this.conversation.id, title: cleaned });
    this.isRenaming = false;
  }

  cancelRename(event?: Event): void {
    event?.stopPropagation();
    this.isRenaming = false;
    this.renameDraft = '';
  }

  onTogglePin(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen = false;
    this.togglePinConversation.emit(this.conversation.id);
  }

  onDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen = false;
    this.deleteConversation.emit(this.conversation.id);
  }

  onMove(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen = false;
    this.moveConversation.emit(this.conversation.id);
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.menuOpen) {
      return;
    }
    const target = event.target as Node | null;
    if (target && !this.host.nativeElement.contains(target)) {
      this.menuOpen = false;
    }
  }
}
