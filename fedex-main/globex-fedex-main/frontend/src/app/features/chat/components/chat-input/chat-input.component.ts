import { CommonModule } from '@angular/common';
import { Component, ElementRef, EventEmitter, Input, Output, ViewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { ChatImageAttachment, ChatSendPayload } from '../../../../core/models/chat-send.model';

const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const ALLOWED_MIME = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
]);

@Component({
  selector: 'app-chat-input',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, TranslatePipe],
  templateUrl: './chat-input.component.html',
  styleUrl: './chat-input.component.scss',
})
export class ChatInputComponent {
  @Input() layout: 'hero' | 'dock' = 'dock';
  @Input() variant: 'default' | 'premium' = 'default';
  @Input() placeholderText = '';
  @Input() showHint = true;
  @Input() disabled = false;

  @Output() send = new EventEmitter<ChatSendPayload>();
  @Output() imageError = new EventEmitter<string>();

  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;

  pendingImage: ChatImageAttachment | null = null;
  imageErrorMessage: string | null = null;

  readonly form = this.fb.nonNullable.group({
    message: ['', [Validators.maxLength(4000)]],
  });

  constructor(private readonly fb: FormBuilder) {}

  get canSend(): boolean {
    if (this.disabled) {
      return false;
    }
    const text = this.form.controls.message.value.trim();
    return Boolean(text || this.pendingImage);
  }

  get pendingIsImage(): boolean {
    return Boolean(this.pendingImage?.previewUrl);
  }

  get pendingIsSpreadsheet(): boolean {
    const mime = this.pendingImage?.mimeType ?? '';
    return mime.includes('spreadsheet') || mime.endsWith('ms-excel');
  }

  openImagePicker(): void {
    this.fileInput?.nativeElement.click();
  }

  onImageSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    this.processFile(file);
  }

  onPaste(event: ClipboardEvent): void {
    const items = event.clipboardData?.items;
    if (!items) {
      return;
    }
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        event.preventDefault();
        const file = item.getAsFile();
        if (file) {
          this.processFile(file);
        }
        return;
      }
    }
  }

  processFile(file: File): void {
    if (!ALLOWED_MIME.has(file.type)) {
      this.imageErrorMessage = 'format';
      this.imageError.emit('format');
      return;
    }
    const isImage = file.type.startsWith('image/');
    const maxBytes = isImage ? MAX_IMAGE_BYTES : MAX_DOCUMENT_BYTES;
    if (file.size > maxBytes) {
      this.imageErrorMessage = 'size';
      this.imageError.emit('size');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string') {
        return;
      }
      const comma = result.indexOf(',');
      const base64 = comma >= 0 ? result.slice(comma + 1) : '';
      if (!base64) {
        return;
      }
      this.pendingImage = {
        base64,
        mimeType: file.type,
        name: file.name,
        previewUrl: isImage ? result : undefined,
        sizeBytes: file.size,
      };
      this.imageErrorMessage = null;
    };
    reader.readAsDataURL(file);
  }

  formatFileSize(bytes: number | undefined): string {
    if (!bytes || bytes < 0) {
      return '';
    }
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  removeImage(): void {
    this.pendingImage = null;
    this.imageErrorMessage = null;
  }

  submit(): void {
    if (!this.canSend) {
      return;
    }
    const text = this.form.controls.message.value.trim();
    const payload: ChatSendPayload = { text };
    if (this.pendingImage) {
      payload.image = this.pendingImage;
    }
    this.send.emit(payload);
    this.form.reset();
    this.pendingImage = null;
    this.imageErrorMessage = null;
  }
}
