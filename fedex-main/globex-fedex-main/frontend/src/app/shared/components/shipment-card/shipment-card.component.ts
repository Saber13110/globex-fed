import { CommonModule, DatePipe } from '@angular/common';

import { HttpErrorResponse } from '@angular/common/http';

import { Component, Input } from '@angular/core';



import { I18nService } from '../../../core/i18n/i18n.service';

import { TranslatePipe } from '../../../core/i18n/translate.pipe';

import { TrackingMapComponent } from '../tracking-map/tracking-map.component';
import { ShipmentSummary } from '../../../core/services/chatbot.service';

import { TrackingService } from '../../../core/services/tracking.service';



@Component({

  selector: 'app-shipment-card',

  standalone: true,

  imports: [CommonModule, DatePipe, TranslatePipe, TrackingMapComponent],

  templateUrl: './shipment-card.component.html',

  styleUrl: './shipment-card.component.scss',

})

export class ShipmentCardComponent {

  @Input({ required: true }) shipment!: ShipmentSummary;

  @Input() compact = false;



  podLoading = false;

  podError = '';

  constructor(

    private readonly tracking: TrackingService,

    private readonly i18n: I18nService,

  ) {}



  get events() {

    return this.shipment.events ?? [];

  }



  get visibilityEvents() {

    return this.shipment.visibility_events ?? [];

  }



  get mapPoints() {
    return this.shipment.map_points ?? [];
  }

  get showTrackingMap(): boolean {
    return !!this.shipment.show_tracking_map;
  }

  get showTimelineSection(): boolean {
    return !!this.shipment.show_timeline && this.events.length > 0;
  }

  get hasEstimatedDelivery(): boolean {
    const eta = this.shipment.estimated_delivery;
    if (!eta) {
      return false;
    }
    const normalized = eta.trim().toLowerCase();
    return normalized !== 'n/a' && normalized !== '—' && normalized !== '-';
  }

  get timelineHasMore(): boolean {
    const total = this.shipment.timeline_total ?? this.events.length;
    return total > this.events.length;
  }

  get mapAvailable(): boolean {
    return !!this.shipment.map_available;
  }

  get isDelivered(): boolean {
    return !!this.shipment.delivered;
  }

  get podInfo() {

    return this.shipment.pod_info ?? null;

  }



  get isSandboxDenied(): boolean {

    return !!this.shipment.sandbox_whitelist_denied;

  }



  get specialHandlings() {

    return this.shipment.special_handlings ?? [];

  }



  formatEventDate(iso: string): string {

    if (!iso?.trim()) {

      return '—';

    }

    const d = new Date(iso);

    if (Number.isNaN(d.getTime())) {

      return iso;

    }

    return d.toLocaleString();

  }



  downloadProof(): void {

    this.podError = '';

    this.podLoading = true;

    this.tracking.downloadProofOfDelivery(this.shipment.tracking_number).subscribe({

      next: (blob) => {

        this.podLoading = false;

        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');

        a.href = url;

        a.download = `preuve-livraison-${this.shipment.tracking_number}.pdf`;

        a.click();

        URL.revokeObjectURL(url);

      },

      error: (err: HttpErrorResponse) => {

        this.podLoading = false;

        const detail = err?.error;

        if (detail instanceof Blob) {

          void detail.text().then((text) => {

            try {

              const parsed = JSON.parse(text) as { detail?: string };

              this.podError = parsed.detail || this.i18n.t('tracking.podError');

            } catch {

              this.podError = this.i18n.t('tracking.podError');

            }

          });

        } else if (typeof detail?.message === 'string') {

          this.podError = detail.message;

        } else {

          this.podError =

            typeof err.error?.detail === 'string' ? err.error.detail : this.i18n.t('tracking.podError');

        }

      },

    });

  }

}


