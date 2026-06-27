import { CommonModule } from '@angular/common';
import { Component, ElementRef, EventEmitter, HostListener, Input, Output } from '@angular/core';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';

@Component({
  selector: 'app-chat-header',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  templateUrl: './chat-header.component.html',
  styleUrl: './chat-header.component.scss',
})
export class ChatHeaderComponent {
  @Input() title = 'Nouvelle conversation';
  @Input() isPinned = false;
  @Input() folderName: string | null = null;

  @Output() shareConversation = new EventEmitter<void>();
  @Output() renameConversation = new EventEmitter<void>();
  @Output() togglePinConversation = new EventEmitter<void>();
  @Output() moveConversation = new EventEmitter<void>();
  @Output() deleteConversation = new EventEmitter<void>();

  menuOpen = false;

  constructor(private readonly host: ElementRef<HTMLElement>) {}

  toggleMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.menuOpen = !this.menuOpen;
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
