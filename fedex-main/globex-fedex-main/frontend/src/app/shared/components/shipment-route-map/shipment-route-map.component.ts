import { AfterViewInit, Component, ElementRef, Input, OnDestroy, ViewChild } from '@angular/core';
import * as L from 'leaflet';

export interface ShipmentMapPoint {
  label: string;
  lat: number;
  lng: number;
  kind?: string;
  description?: string;
}

@Component({
  selector: 'app-shipment-route-map',
  standalone: true,
  template: `<div #mapHost class="route-map"></div>`,
  styleUrl: './shipment-route-map.component.scss',
})
export class ShipmentRouteMapComponent implements AfterViewInit, OnDestroy {
  @Input({ required: true }) points: ShipmentMapPoint[] = [];
  @Input() ariaLabel = 'Carte du parcours du colis';

  @ViewChild('mapHost', { static: true }) mapHost!: ElementRef<HTMLDivElement>;

  private map?: L.Map;

  ngAfterViewInit(): void {
    if (!this.points.length) {
      return;
    }
    const host = this.mapHost.nativeElement;
    host.setAttribute('role', 'img');
    host.setAttribute('aria-label', this.ariaLabel);

    this.map = L.map(host, { scrollWheelZoom: true, zoomControl: true });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap',
    }).addTo(this.map);

    const latlngs: L.LatLngExpression[] = [];
    for (const point of this.points) {
      const color =
        point.kind === 'current' ? '#7c3aed' : point.kind === 'origin' ? '#059669' : '#2563eb';
      const marker = L.circleMarker([point.lat, point.lng], {
        radius: 9,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.9,
      });
      const popup = point.description
        ? `<strong>${point.label}</strong><br>${point.description}`
        : `<strong>${point.label}</strong>`;
      marker.bindPopup(popup);
      marker.addTo(this.map);
      latlngs.push([point.lat, point.lng]);
    }

    if (latlngs.length > 1) {
      L.polyline(latlngs, { color: '#7c3aed', weight: 3, opacity: 0.75, dashArray: '6 8' }).addTo(
        this.map,
      );
    }

    if (latlngs.length === 1) {
      this.map.setView(latlngs[0], 10);
    } else {
      this.map.fitBounds(L.latLngBounds(latlngs), { padding: [28, 28] });
    }
  }

  ngOnDestroy(): void {
    this.map?.remove();
    this.map = undefined;
  }
}
