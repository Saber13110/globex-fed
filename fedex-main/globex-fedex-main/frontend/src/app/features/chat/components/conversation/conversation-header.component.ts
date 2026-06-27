import { CommonModule } from '@angular/common';
import { Component, ElementRef, EventEmitter, HostListener, Input, Output, inject } from '@angular/core';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { I18nService } from '../../../../core/i18n/i18n.service';
import { formatRelativeActivity } from './conversation.utils';

@Component({
  selector: 'app-conversation-header',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  templateUrl: './conversation-header.component.html',
  styleUrl: './conversation-header.component.scss',
})
export class ConversationHeaderComponent {
  private readonly i18n = inject(I18nService);
  private readonly host = inject(ElementRef<HTMLElement>);

  @Input({ required: true }) title = '';
  @Input() sessionUpdatedAt = '';
  @Input() isPinned = false;
  @Input() exportLoading = false;

  @Output() shareConversation = new EventEmitter<void>();
  @Output() exportConversation = new EventEmitter<void>();
  @Output() renameConversation = new EventEmitter<void>();
  @Output() togglePinConversation = new EventEmitter<void>();
  @Output() moveConversation = new EventEmitter<void>();
  @Output() deleteConversation = new EventEmitter<void>();

  menuOpen = false;

  metaLine(): string {
    return `${this.i18n.t('conversation.aiAssistant')} • ${this.i18n.t('conversation.status.active')}`;
  }

  activityLine(): string {
    const relative = formatRelativeActivity(
      this.sessionUpdatedAt,
      (key: string, params?: Record<string, string>) => this.i18n.t(key, params),
    );
    if (!relative) {
      return '';
    }
    return this.i18n.t('conversation.lastActivityShort', { time: relative });
  }

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
