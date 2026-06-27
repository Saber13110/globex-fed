import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import {
  EmployeePortalService,
  EmployeeTrackingItem,
} from '../../../../core/services/employee-portal.service';

@Component({
  selector: 'app-employee-tracking-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-tracking-page.component.html',
  styleUrl: './employee-tracking-page.component.scss',
})
export class EmployeeTrackingPageComponent implements OnInit {
  q = '';
  items: EmployeeTrackingItem[] = [];
  loading = true;
  page = 1;
  pageSize = 12;
  total = 0;

  readonly heroBanner = 'assets/employee/hero-tracking-ops-v3.png';

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.total / this.pageSize));
  }

  ngOnInit(): void {
    this.q = this.route.snapshot.queryParamMap.get('q') || '';
    this.loadShipments();
  }

  loadShipments(): void {
    this.loading = true;
    const params: Record<string, string> = {
      page: String(this.page),
      limit: String(this.pageSize),
    };
    if (this.q.trim()) params['q'] = this.q.trim();
    this.employee.listShipments(params).subscribe({
      next: (r) => {
        this.items = r.items;
        this.total = r.total;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  search(): void {
    this.page = 1;
    this.loadShipments();
  }

  goToPage(p: number): void {
    if (p < 1 || p > this.totalPages) return;
    this.page = p;
    this.loadShipments();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  openShipment(item: EmployeeTrackingItem): void {
    void this.router.navigate(['/employee/tracking', item.tracking_number]);
  }

  statusClass(category: string | undefined): string {
    return `ship-ops-card__status--${category || 'pending'}`;
  }
}
