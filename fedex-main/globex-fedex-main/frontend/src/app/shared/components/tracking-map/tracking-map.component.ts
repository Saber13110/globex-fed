import { CommonModule, DatePipe } from '@angular/common';
import {
  AfterViewInit,
  Component,
  ElementRef,
  Input,
  OnChanges,
  OnDestroy,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import * as L from 'leaflet';

import { TranslatePipe } from '../../../core/i18n/translate.pipe';
import { TrackingEvent, TrackingMapPoint } from '../../../core/services/chatbot.service';

@Component({
  selector: 'app-tracking-map',
  standalone: true,
  imports: [CommonModule, DatePipe, TranslatePipe],
  templateUrl: './tracking-map.component.html',
  styleUrl: './tracking-map.component.scss',
})
export class TrackingMapComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input({ required: true }) mapPoints: TrackingMapPoint[] = [];
  @Input() events: TrackingEvent[] = [];
  @Input() delivered = false;
  @Input() mapAvailable = false;
  @Input() trackingNumber = '';
  @Input() showTimeline = true;

  @ViewChild('mapHost') mapHost?: ElementRef<HTMLDivElement>;

  private map?: L.Map;
  private mapReady = false;

  get geocodedPoints(): TrackingMapPoint[] {
    return this.mapPoints.filter(
      (p) => typeof p.latitude === 'number' && typeof p.longitude === 'number',
    );
  }

  get showMap(): boolean {
    return this.mapAvailable && this.geocodedPoints.length > 0;
  }

  get timelineEvents(): TrackingEvent[] {
    if (this.events.length) {
      return this.events;
    }
    return this.mapPoints.map((p) => ({
      at: p.date,
      description: p.eventDescription,
      location: p.label || [p.city, p.stateOrProvinceCode, p.countryName].filter(Boolean).join(', '),
      city: p.city,
      state_or_province: p.stateOrProvinceCode,
      country: p.countryName,
    }));
  }

  ngAfterViewInit(): void {
    this.mapReady = true;
    setTimeout(() => this.renderMap(), 0);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.mapReady && (changes['mapPoints'] || changes['mapAvailable'])) {
      setTimeout(() => this.renderMap(), 0);
    }
  }

  ngOnDestroy(): void {
    this.destroyMap();
  }

  formatEventDate(iso: string): string {
    if (!iso?.trim()) {
      return '—';
    }
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  isDeliveredStep(index: number, ev: TrackingEvent): boolean {
    if (!this.delivered) {
      return false;
    }
    return index === 0;
  }

  private destroyMap(): void {
    this.map?.remove();
    this.map = undefined;
  }

  private renderMap(): void {
    if (!this.showMap || !this.mapHost?.nativeElement) {
      this.destroyMap();
      return;
    }

    this.destroyMap();
    const host = this.mapHost.nativeElement;
    this.map = L.map(host, { scrollWheelZoom: true, zoomControl: true });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap',
    }).addTo(this.map);

    const latlngs: L.LatLngExpression[] = [];
    for (const point of this.geocodedPoints) {
      const lat = point.latitude as number;
      const lng = point.longitude as number;
      const icon = L.divIcon({
        className: 'tracking-map-marker-wrap',
        html: `<span class="tracking-map-marker tracking-map-marker--${point.kind || 'transit'}">${point.step}</span>`,
        iconSize: [30, 30],
        iconAnchor: [15, 15],
      });
      const marker = L.marker([lat, lng], { icon });
      const place = [point.city, point.stateOrProvinceCode, point.countryName].filter(Boolean).join(', ');
      const title =
        point.kind === 'delivered'
          ? `<strong>Livré</strong><br>`
          : point.kind === 'current'
            ? `<strong>Position actuelle</strong><br>`
            : '';
      marker.bindPopup(
        `${title}<strong>${this.formatEventDate(point.date)}</strong><br>` +
          `${point.eventDescription}<br>` +
          `${place || point.label}`,
      );
      marker.addTo(this.map);
      latlngs.push([lat, lng]);
    }

    if (latlngs.length > 1) {
      L.polyline(latlngs, { color: '#7c3aed', weight: 3, opacity: 0.8 }).addTo(this.map);
      this.map.fitBounds(L.latLngBounds(latlngs), { padding: [32, 32] });
    } else if (latlngs.length === 1) {
      this.map.setView(latlngs[0], 10);
    }
    setTimeout(() => this.map?.invalidateSize(), 100);
  }
}
