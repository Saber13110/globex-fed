import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import {
  LucideArrowLeft,
  LucideClock,
  LucideFilter,
  LucidePackage,
  LucideSearch,
  provideLucideIcons,
} from '@lucide/angular';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { EmployeePortalService, EmployeeTrackingItem } from '../../../../core/services/employee-portal.service';

@Component({
  selector: 'app-employee-tracking-history-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe, LucideArrowLeft, LucideClock, LucidePackage, LucideSearch, LucideFilter],
  providers: [provideLucideIcons(LucideArrowLeft, LucideClock, LucidePackage, LucideSearch, LucideFilter)],
  templateUrl: './employee-tracking-history-page.component.html',
  styleUrl: './employee-tracking-history-page.component.scss',
})
export class EmployeeTrackingHistoryPageComponent implements OnInit {
  items: EmployeeTrackingItem[] = [];
  filtered: EmployeeTrackingItem[] = [];
  q = '';
  statusFilter = 'all';
  loading = true;

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.employee.listShipments({ limit: '100' }).subscribe({
      next: (r) => {
        this.items = r.items;
        this.applyFilters();
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  applyFilters(): void {
    let list = [...this.items];
    if (this.q.trim()) {
      const term = this.q.trim().toLowerCase();
      list = list.filter(
        (i) =>
          i.tracking_number.toLowerCase().includes(term) ||
          (i.client_name || '').toLowerCase().includes(term) ||
          (i.status || '').toLowerCase().includes(term),
      );
    }
    if (this.statusFilter === 'active') {
      list = list.filter((i) => !['delivered', 'livré', 'cancelled', 'annulé'].includes((i.status || '').toLowerCase()));
    } else if (this.statusFilter === 'delivered') {
      list = list.filter((i) => ['delivered', 'livré'].includes((i.status || '').toLowerCase()));
    } else if (this.statusFilter === 'exception') {
      list = list.filter((i) => i.is_exception);
    }
    this.filtered = list;
  }

  openShipment(item: EmployeeTrackingItem): void {
    void this.router.navigate(['/employee/tracking', item.tracking_number]);
  }

  statusClass(category: string | undefined): string {
    return `th-status--${category || 'pending'}`;
  }
}
