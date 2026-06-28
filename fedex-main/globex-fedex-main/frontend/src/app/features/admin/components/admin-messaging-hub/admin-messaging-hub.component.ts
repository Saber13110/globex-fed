import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  AdminEmployeeChatListItem,
  AdminEmployeeChatMessage,
  AdminService,
  AdminSupportTicketSummary,
} from '../../../../core/services/admin.service';
import { SupportService } from '../../../../core/services/support.service';

type RecipientMode = 'employee' | 'user';

@Component({
  selector: 'app-admin-messaging-hub',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule],
  templateUrl: './admin-messaging-hub.component.html',
  styleUrl: './admin-messaging-hub.component.scss',
})
export class AdminMessagingHubComponent implements OnInit {
  @Output() openUserTicket = new EventEmitter<number>();

  readonly mode = signal<RecipientMode>('employee');
  readonly employees = signal<AdminEmployeeChatListItem[]>([]);
  readonly tickets = signal<AdminSupportTicketSummary[]>([]);
  readonly selectedEmployeeId = signal<number | null>(null);
  readonly messages = signal<AdminEmployeeChatMessage[]>([]);
  readonly loading = signal(true);
  readonly messagesLoading = signal(false);
  readonly submitting = signal(false);

  searchQ = '';
  draft = '';
  attachmentUrl: string | null = null;
  attachmentName = '';
  uploadingAttachment = false;

  constructor(
    private readonly admin: AdminService,
    private readonly support: SupportService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.reload();
  }

  setMode(mode: RecipientMode): void {
    this.mode.set(mode);
    this.selectedEmployeeId.set(null);
    this.messages.set([]);
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    if (this.mode() === 'employee') {
      this.admin.listEmployeeChats(this.searchQ.trim() || undefined).subscribe({
        next: (rows) => {
          this.employees.set(rows);
          this.loading.set(false);
          const first = rows[0];
          if (first && !this.selectedEmployeeId()) {
            this.selectEmployee(first.id);
          }
        },
        error: () => this.loading.set(false),
      });
      return;
    }
    this.admin.listSupportTickets('open').subscribe({
      next: (res) => {
        const items = res.items.filter((t) => {
          const q = this.searchQ.trim().toLowerCase();
          if (!q) return true;
          return t.subject.toLowerCase().includes(q) || t.message.toLowerCase().includes(q);
        });
        this.tickets.set(items);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  selectEmployee(id: number): void {
    this.selectedEmployeeId.set(id);
    this.messagesLoading.set(true);
    this.admin.getEmployeeChatMessages(id).subscribe({
      next: (res) => {
        this.messages.set(res.items);
        this.messagesLoading.set(false);
        this.admin.listEmployeeChats().subscribe({
          next: (rows) => this.employees.set(rows),
        });
      },
      error: () => {
        this.messagesLoading.set(false);
        this.toast('Impossible de charger les messages.', 'error');
      },
    });
  }

  sendToEmployee(): void {
    const id = this.selectedEmployeeId();
    const body = this.draft.trim();
    if (!id || (!body && !this.attachmentUrl)) return;
    this.submitting.set(true);
    this.admin.sendEmployeeChatMessage(id, body, this.attachmentUrl).subscribe({
      next: (msg) => {
        this.messages.update((rows) => [...rows, msg]);
        this.draft = '';
        this.clearAttachment();
        this.submitting.set(false);
        this.reload();
      },
      error: () => {
        this.submitting.set(false);
        this.toast('Échec de l\'envoi.', 'error');
      },
    });
  }

  openTicket(id: number): void {
    this.openUserTicket.emit(id);
  }

  selectedEmployee(): AdminEmployeeChatListItem | null {
    const id = this.selectedEmployeeId();
    return this.employees().find((e) => e.id === id) ?? null;
  }

  isAdmin(msg: AdminEmployeeChatMessage): boolean {
    return msg.sender_role === 'admin';
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
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

  private toast(message: string, kind: 'success' | 'error'): void {
    this.snack.open(message, 'OK', {
      duration: 3200,
      panelClass: kind === 'error' ? 'snack-error' : 'snack-success',
    });
  }
}
