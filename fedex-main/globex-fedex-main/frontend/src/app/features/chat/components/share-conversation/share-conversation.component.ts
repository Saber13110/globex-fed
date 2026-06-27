import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-share-conversation',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './share-conversation.component.html',
  styleUrl: './share-conversation.component.scss',
})
export class ShareConversationComponent {
  @Input({ required: true }) conversationId = '';
  @Input({ required: true }) conversationTitle = '';
  @Input() shareUrl = '';
  @Input() loading = false;
  @Output() close = new EventEmitter<void>();
  @Output() includeTrackingDetailsChange = new EventEmitter<boolean>();
  @Output() regenerateLink = new EventEmitter<void>();

  includeTrackingDetails = false;
  copied = false;

  onToggleIncludeTracking(value: boolean): void {
    this.includeTrackingDetails = value;
    this.includeTrackingDetailsChange.emit(value);
    this.regenerateLink.emit();
  }

  async copyLink(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.shareUrl);
      this.copied = true;
      setTimeout(() => {
        this.copied = false;
      }, 2000);
    } catch {
      this.copied = false;
    }
  }
}
