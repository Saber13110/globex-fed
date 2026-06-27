import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AdminService, AdminSupportTicketSummary } from '../../../../core/services/admin.service';
import { AdminSupportDrawerComponent } from '../admin-support-drawer/admin-support-drawer.component';

@Component({
  selector: 'app-admin-support-tickets',
  standalone: true,
  imports: [CommonModule, FormsModule, AdminSupportDrawerComponent],
  templateUrl: './admin-support-tickets.component.html',
  styleUrl: './admin-support-tickets.component.scss',
})
export class AdminSupportTicketsComponent implements OnInit {
  readonly tickets = signal<AdminSupportTicketSummary[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly drawerOpen = signal(false);
  readonly activeTicketId = signal<number | null>(null);
  statusFilter = 'all';

  constructor(private readonly admin: AdminService) {}

  ngOnInit(): void {
    this.loadTickets();
  }

  loadTickets(): void {
    this.loading.set(true);
    this.admin.listSupportTickets(this.statusFilter).subscribe({
      next: (res) => {
        this.tickets.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Impossible de charger les tickets support.');
      },
    });
  }

  openTicket(id: number): void {
    this.activeTicketId.set(id);
    this.drawerOpen.set(true);
  }

  closeDrawer(): void {
    this.drawerOpen.set(false);
    this.activeTicketId.set(null);
  }

  onTicketUpdated(): void {
    this.loadTickets();
  }
}
