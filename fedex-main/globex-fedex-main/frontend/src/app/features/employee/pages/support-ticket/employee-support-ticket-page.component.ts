import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { EmployeePortalService } from '../../../../core/services/employee-portal.service';
import { SupportService, SupportTicketDetail, SupportTicketMessage } from '../../../../core/services/support.service';

@Component({
  selector: 'app-employee-support-ticket-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-support-ticket-page.component.html',
  styleUrls: ['../../employee-workspace.scss'],
})
export class EmployeeSupportTicketPageComponent implements OnInit {
  ticket: (SupportTicketDetail & { user_name?: string; user_email?: string }) | null = null;
  reply = '';
  sending = false;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly employee: EmployeePortalService,
    private readonly support: SupportService,
  ) {}

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('ticketId'));
    this.load(id);
  }

  load(id: number): void {
    this.employee.getTicket(id).subscribe({ next: (t) => (this.ticket = t) });
  }

  sendReply(): void {
    if (!this.ticket || !this.reply.trim() || this.sending) return;
    this.sending = true;
    this.employee.replyTicket(this.ticket.id, this.reply.trim()).subscribe({
      next: (msg: SupportTicketMessage) => {
        this.ticket!.messages = [...(this.ticket!.messages || []), msg];
        this.reply = '';
        this.sending = false;
      },
      error: () => (this.sending = false),
    });
  }

  setStatus(status: string): void {
    if (!this.ticket) return;
    this.employee.updateTicketStatus(this.ticket.id, status).subscribe({
      next: (t) => {
        if (this.ticket) this.ticket.status = t.status;
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !this.ticket) return;
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.employee.replyTicket(this.ticket!.id, this.reply.trim() || 'Pièce jointe', res.url).subscribe({
          next: () => this.load(this.ticket!.id),
        });
      },
    });
    input.value = '';
  }

  openAttachment(url: string): void {
    this.support.openAttachment(url).subscribe({
      error: () => window.alert('Impossible d\'ouvrir la pièce jointe.'),
    });
  }
}
