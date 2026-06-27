import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  AdminEmployeeChatMessage,
  AdminService,
} from '../../../../core/services/admin.service';
import { SupportService } from '../../../../core/services/support.service';
import { AdminUserSuspendActionsComponent } from '../admin-user-suspend-actions/admin-user-suspend-actions.component';

@Component({
  selector: 'app-admin-employee-chat-drawer',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule, AdminUserSuspendActionsComponent],
  templateUrl: './admin-employee-chat-drawer.component.html',
  styleUrl: './admin-employee-chat-drawer.component.scss',
})
export class AdminEmployeeChatDrawerComponent implements OnChanges {
  @Input() open = false;
  @Input() employeeId: number | null = null;
  @Output() closed = new EventEmitter<void>();
  @Output() updated = new EventEmitter<void>();

  readonly messages = signal<AdminEmployeeChatMessage[]>([]);
  readonly employeeName = signal('');
  readonly employeeEmail = signal('');
  readonly employeeStatus = signal('active');
  readonly loading = signal(false);
  readonly submitting = signal(false);

  draft = '';
  attachmentUrl: string | null = null;
  attachmentName = '';
  uploadingAttachment = false;

  constructor(
    private readonly admin: AdminService,
    private readonly support: SupportService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnChanges(): void {
    if (this.open && this.employeeId) {
      this.load(this.employeeId);
    }
  }

  load(id: number): void {
    this.loading.set(true);
    this.admin.listEmployeeChats().subscribe({
      next: (rows) => {
        const row = rows.find((r) => r.id === id);
        if (row) {
          this.employeeName.set(row.full_name);
          this.employeeEmail.set(row.email);
        }
      },
    });
    if (id) {
      this.admin.getUserDetail(id).subscribe({
        next: (u) => this.employeeStatus.set(u.status),
        error: () => this.employeeStatus.set('active'),
      });
    }
    this.admin.getEmployeeChatMessages(id).subscribe({
      next: (res) => {
        this.messages.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.toast('Impossible de charger la conversation.', 'error');
      },
    });
  }

  close(): void {
    this.messages.set([]);
    this.draft = '';
    this.clearAttachment();
    this.closed.emit();
  }

  onEmployeeSuspended(): void {
    const id = this.employeeId;
    if (id) {
      this.admin.getUserDetail(id).subscribe({
        next: (u) => this.employeeStatus.set(u.status),
      });
    }
    this.updated.emit();
  }

  send(): void {
    const id = this.employeeId;
    const body = this.draft.trim();
    if (!id || (!body && !this.attachmentUrl)) return;
    this.submitting.set(true);
    this.admin.sendEmployeeChatMessage(id, body, this.attachmentUrl).subscribe({
      next: (msg) => {
        this.messages.update((rows) => [...rows, msg]);
        this.draft = '';
        this.clearAttachment();
        this.submitting.set(false);
        this.updated.emit();
      },
      error: () => {
        this.submitting.set(false);
        this.toast('Échec de l\'envoi.', 'error');
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const err = this.support.validateAttachmentFile(file);
    if (err) {
      this.toast(err === 'size' ? 'Fichier trop volumineux.' : 'Type de fichier non autorisé.', 'error');
      input.value = '';
      return;
    }
    this.uploadingAttachment = true;
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.attachmentUrl = res.url;
        this.attachmentName = file.name;
        this.uploadingAttachment = false;
      },
      error: () => {
        this.uploadingAttachment = false;
        this.toast('Échec du téléversement.', 'error');
      },
    });
    input.value = '';
  }

  clearAttachment(): void {
    this.attachmentUrl = null;
    this.attachmentName = '';
  }

  openAttachment(url: string, event: Event): void {
    event.stopPropagation();
    this.support.openAttachment(url).subscribe({
      error: () => this.toast('Impossible d\'ouvrir la pièce jointe.', 'error'),
    });
  }

  displayAttachmentName(url: string): string {
    return this.support.attachmentDisplayName(url);
  }

  isAdmin(msg: AdminEmployeeChatMessage): boolean {
    return msg.sender_role === 'admin';
  }

  private toast(message: string, kind: 'success' | 'error'): void {
    this.snack.open(message, 'OK', {
      duration: 3200,
      panelClass: kind === 'error' ? 'snack-error' : 'snack-success',
    });
  }
}
