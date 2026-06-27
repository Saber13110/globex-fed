import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  AdminService,
  AdminSupportTicketDetail,
  AdminSupportTicketMessage,
  AdminSupportTicketSummary,
} from '../../../../core/services/admin.service';
import { SupportService } from '../../../../core/services/support.service';

@Component({
  selector: 'app-admin-support-drawer',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule],
  templateUrl: './admin-support-drawer.component.html',
  styleUrl: './admin-support-drawer.component.scss',
})
export class AdminSupportDrawerComponent implements OnChanges {
  @Input() open = false;
  @Input() ticketId: number | null = null;
  @Output() closed = new EventEmitter<void>();
  @Output() updated = new EventEmitter<void>();

  readonly ticket = signal<AdminSupportTicketDetail | null>(null);
  readonly loading = signal(false);
  readonly submitting = signal(false);

  replyMessage = '';
  attachmentUrl: string | null = null;
  attachmentName = '';
  uploadingAttachment = false;

  constructor(
    private readonly admin: AdminService,
    private readonly support: SupportService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnChanges(): void {
    if (this.open && this.ticketId) {
      this.loadTicket(this.ticketId);
    }
  }

  loadTicket(id: number): void {
    this.loading.set(true);
    this.admin.getSupportTicket(id).subscribe({
      next: (row: AdminSupportTicketDetail) => {
        this.ticket.set(row);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.toast('Impossible de charger le ticket.', 'error');
      },
    });
  }

  close(): void {
    this.ticket.set(null);
    this.replyMessage = '';
    this.clearAttachment();
    this.closed.emit();
  }

  sendReply(): void {
    const row = this.ticket();
    const message = this.replyMessage.trim();
    if (!row || (!message && !this.attachmentUrl)) return;
    this.submitting.set(true);
    this.admin.replySupportTicket(row.id, message, this.attachmentUrl).subscribe({
      next: (msg: AdminSupportTicketMessage) => {
        this.submitting.set(false);
        this.replyMessage = '';
        this.clearAttachment();
        this.ticket.set({
          ...row,
          status: row.status === 'open' ? 'pending' : row.status,
          messages: [...row.messages, msg],
        });
        this.toast('Réponse envoyée au client.', 'success');
        this.updated.emit();
      },
      error: () => {
        this.submitting.set(false);
        this.toast('Échec de l\'envoi.', 'error');
      },
    });
  }

  markResolved(): void {
    const row = this.ticket();
    if (!row) return;
    this.admin.updateSupportTicketStatus(row.id, 'resolved').subscribe({
      next: (updated: AdminSupportTicketSummary) => {
        this.ticket.set({ ...row, status: updated.status });
        this.toast('Ticket marqué résolu.', 'success');
        this.updated.emit();
      },
      error: () => this.toast('Échec de la mise à jour.', 'error'),
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;

    const err = this.support.validateAttachmentFile(file);
    if (err === 'type') {
      this.toast('Type de fichier non autorisé.', 'error');
      return;
    }
    if (err === 'size') {
      this.toast('Fichier trop volumineux (max 15 Mo).', 'error');
      return;
    }

    this.uploadingAttachment = true;
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.uploadingAttachment = false;
        this.attachmentUrl = res.url;
        this.attachmentName = res.filename;
      },
      error: () => {
        this.uploadingAttachment = false;
        this.toast('Échec du téléversement du fichier.', 'error');
      },
    });
  }

  clearAttachment(): void {
    this.attachmentUrl = null;
    this.attachmentName = '';
  }

  displayAttachmentName(url: string): string {
    return this.support.attachmentDisplayName(url);
  }

  openAttachment(url: string, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    this.support.openAttachment(url).subscribe({
      error: () => this.toast('Impossible d\'ouvrir le fichier.', 'error'),
    });
  }

  priorityClass(priority?: string): string {
    if (priority === 'high') return 'asd-badge--high';
    if (priority === 'low') return 'asd-badge--low';
    return 'asd-badge--medium';
  }

  statusClass(status: string): string {
    return `asd-badge--status-${status}`;
  }

  private toast(msg: string, type: 'success' | 'error'): void {
    this.snack.open(msg, 'Fermer', {
      duration: 4000,
      panelClass: type === 'success' ? 'set-snack--ok' : 'set-snack--err',
      horizontalPosition: 'end',
      verticalPosition: 'top',
    });
  }
}
