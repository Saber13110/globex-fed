import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { EmployeePortalService, EmployeeShipmentDetail } from '../../../../core/services/employee-portal.service';

@Component({
  selector: 'app-employee-shipment-detail-page',
  standalone: true,
  imports: [CommonModule, RouterLink, TranslatePipe],
  templateUrl: './employee-shipment-detail-page.component.html',
  styleUrl: './employee-shipment-detail-page.component.scss',
})
export class EmployeeShipmentDetailPageComponent implements OnInit {
  detail: EmployeeShipmentDetail | null = null;
  loading = true;
  error = false;
  copied = false;
  showAllEvents = false;
  showContactModal = false;
  toast = '';
  trackingNumber = '';

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly employee: EmployeePortalService,
  ) {}

  get visibleTimeline() {
    if (!this.detail) return [];
    return this.showAllEvents ? this.detail.timeline : this.detail.timeline.slice(0, 6);
  }

  ngOnInit(): void {
    this.trackingNumber = this.route.snapshot.paramMap.get('trackingNumber') || '';
    if (!this.trackingNumber) {
      void this.router.navigate(['/employee/tracking']);
      return;
    }
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = false;
    this.employee.getShipmentDetail(this.trackingNumber).subscribe({
      next: (d) => {
        this.detail = d;
        this.loading = false;
      },
      error: () => {
        this.error = true;
        this.loading = false;
      },
    });
  }

  statusClass(category: string): string {
    return `sws-status--${category || 'pending'}`;
  }

  riskClass(risk: string): string {
    return `sws-health__risk--${risk || 'low'}`;
  }

  timelineIcon(kind: string): string {
    if (kind === 'delivered') return 'delivered';
    if (kind === 'exception') return 'alert';
    if (kind === 'pickup' || kind === 'out_for_delivery') return 'truck';
    if (kind === 'created') return 'created';
    return 'facility';
  }

  copyTracking(): void {
    if (!this.detail) return;
    void navigator.clipboard.writeText(this.detail.tracking_number);
    this.copied = true;
    this.flash('employee.shipOps.copied');
    setTimeout(() => (this.copied = false), 2000);
  }

  downloadPod(): void {
    if (!this.detail?.pod_available) return;
    this.employee.downloadShipmentPod(this.detail.tracking_number);
    this.flash('employee.shipOps.downloadStarted');
  }

  exportTracking(): void {
    if (!this.detail) return;
    this.employee.exportShipment(this.detail.tracking_number, 'pdf');
    this.flash('employee.shipOps.exportStarted');
  }

  contactClient(): void {
    this.showContactModal = true;
  }

  sendEmail(): void {
    if (!this.detail?.client_email) return;
    window.location.href = `mailto:${this.detail.client_email}?subject=Shipment ${this.detail.tracking_number}`;
    this.showContactModal = false;
  }

  createTicket(): void {
    if (!this.detail) return;
    void this.router.navigate(['/employee/support'], {
      queryParams: {
        q: this.detail.tracking_number,
        clientId: this.detail.client_id ?? undefined,
      },
    });
  }

  openAiAssistant(prompt?: string): void {
    void this.router.navigate(['/employee/ai-assistant'], {
      queryParams: {
        q: prompt || `Summarize shipment ${this.trackingNumber}`,
      },
    });
  }

  private flash(key: string): void {
    this.toast = key;
    setTimeout(() => (this.toast = ''), 3000);
  }
}
