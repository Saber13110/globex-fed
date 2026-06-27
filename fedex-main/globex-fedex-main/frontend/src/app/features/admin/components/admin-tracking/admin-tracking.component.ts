import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  CommandCenterPayload,
  CommandCenterService,
  LiveShipmentItem,
} from '../../../../core/services/command-center.service';
import { resolveShipmentFlag } from '../../../../core/utils/country-flags.util';

type StatusFilter = 'all' | 'in_transit' | 'delivered' | 'delayed';

interface TrackingKpi {
  label: string;
  value: string;
  trend: string;
  trendUp: boolean;
  icon: string;
  tone: 'purple' | 'blue' | 'green' | 'orange';
}

@Component({
  selector: 'app-admin-tracking',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-tracking.component.html',
  styleUrl: './admin-tracking.component.scss',
})
export class AdminTrackingComponent implements OnInit {
  @Input() initialSearch = '';
  @Input() initialShipmentId: number | null = null;

  readonly heroPlane = 'assets/admin/tracking-hero-plane.png?v=4';
  readonly heroPlaneWebp = 'assets/admin/tracking-hero-plane.webp?v=1';
  readonly worldMap = 'assets/admin/world-map-overlay.png';

  readonly loading = signal(true);
  readonly data = signal<CommandCenterPayload | null>(null);
  readonly search = signal('');
  readonly statusFilter = signal<StatusFilter>('all');
  readonly selectedId = signal<number | null>(null);
  readonly filtersOpen = signal(false);

  readonly statusTabs: { id: StatusFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'in_transit', label: 'In Transit' },
    { id: 'delivered', label: 'Delivered' },
    { id: 'delayed', label: 'Delayed' },
  ];

  readonly shipments = computed(() => this.data()?.live_shipments ?? []);

  readonly filteredShipments = computed(() => {
    const q = this.search().trim().toLowerCase();
    const filter = this.statusFilter();
    return this.shipments().filter((s) => {
      if (filter !== 'all' && s.status_key !== filter) return false;
      if (!q) return true;
      return (
        s.tracking_number.toLowerCase().includes(q) ||
        s.origin.toLowerCase().includes(q) ||
        s.destination.toLowerCase().includes(q) ||
        s.route.toLowerCase().includes(q)
      );
    });
  });

  readonly selected = computed(() => {
    const id = this.selectedId();
    const visible = this.filteredShipments();
    if (id != null) {
      const match = visible.find((s) => s.id === id) ?? this.shipments().find((s) => s.id === id);
      if (match) return match;
    }
    return visible[0] ?? null;
  });

  readonly kpis = computed((): TrackingKpi[] => {
    const items = this.shipments();
    const total = items.length || 12458;
    const inTransit = items.filter((s) => s.status_key === 'in_transit').length || 3241;
    const delivered = items.filter((s) => s.status_key === 'delivered').length || 9175;
    const delayed = items.filter((s) => s.status_key === 'delayed').length || 42;
    return [
      { label: 'Total Shipments', value: this.fmt(total), trend: '+12.5%', trendUp: true, icon: 'box', tone: 'purple' },
      { label: 'In Transit', value: this.fmt(inTransit), trend: '+8.2%', trendUp: true, icon: 'truck', tone: 'blue' },
      { label: 'Delivered', value: this.fmt(delivered), trend: '+15.1%', trendUp: true, icon: 'check', tone: 'green' },
      { label: 'Delayed', value: this.fmt(delayed), trend: '-3.4%', trendUp: false, icon: 'alert', tone: 'orange' },
    ];
  });

  constructor(private readonly commandCenter: CommandCenterService) {}

  ngOnInit(): void {
    if (this.initialSearch.trim()) {
      this.search.set(this.initialSearch.trim());
    }
    this.commandCenter.getPayload().subscribe({
      next: (payload) => {
        this.data.set(payload);
        this.loading.set(false);
        const preferredId = this.initialShipmentId ?? payload.live_shipments[0]?.id ?? null;
        if (preferredId != null) {
          this.selectedId.set(preferredId);
        }
      },
      error: () => {
        this.data.set(this.demoPayload());
        this.loading.set(false);
        this.selectedId.set(1);
      },
    });
  }

  resolveFlag(flag: string, place: string): string {
    return resolveShipmentFlag(flag, place);
  }

  selectShipment(s: LiveShipmentItem): void {
    this.selectedId.set(s.id);
  }

  detailInsight(s: LiveShipmentItem): { title: string; message: string; tone: 'success' | 'warning' | 'info' } {
    if (s.status_key === 'delivered') {
      return {
        title: 'Livraison confirmée',
        message: 'Ce colis a été livré avec succès. Aucune action requise.',
        tone: 'success',
      };
    }
    if (s.status_key === 'delayed') {
      return {
        title: 'Retard signalé',
        message: `Expédition en retard sur la route ${s.route}. Surveillance active du hub FedEx.`,
        tone: 'warning',
      };
    }
    return {
      title: 'En transit',
      message: `Colis en route vers ${s.destination}. ETA estimée : ${s.eta_label}.`,
      tone: 'info',
    };
  }

  formatUpdatedAt(iso: string): string {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString('fr-FR', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  serviceLabel(carrier: string): string {
    return carrier.toLowerCase().includes('ground') ? 'FedEx Ground' : 'FedEx Express';
  }

  statusClass(key: string): string {
    if (key === 'delivered') return 'trk-status--delivered';
    if (key === 'delayed') return 'trk-status--delayed';
    return 'trk-status--transit';
  }

  carrierClass(carrier: string): string {
    return carrier.toLowerCase().includes('ground') ? 'trk-carrier--ground' : 'trk-carrier--express';
  }

  private fmt(n: number): string {
    return n >= 1000 ? n.toLocaleString('en-US') : String(n);
  }

  private demoPayload(): CommandCenterPayload {
    return {
      hero_stats: [],
      today_overview: [],
      executive_insights: [],
      kpis: [],
      live_shipments: [
        { id: 1, route: 'CDG → JFK', origin: 'Paris', destination: 'New York', origin_flag: '🇫🇷', destination_flag: '🇺🇸', carrier: 'FedEx Express', tracking_number: '7489 2345 6789', status: 'In Transit', status_key: 'in_transit', eta_label: '14:30', progress_percent: 68, updated_at: new Date().toISOString() },
        { id: 2, route: 'LHR → DXB', origin: 'London', destination: 'Dubai', origin_flag: '🇬🇧', destination_flag: '🇦🇪', carrier: 'FedEx Express', tracking_number: '7489 1122 3344', status: 'Delivered', status_key: 'delivered', eta_label: 'Done', progress_percent: 100, updated_at: new Date().toISOString() },
        { id: 3, route: 'CMN → CDG', origin: 'Casablanca', destination: 'Paris', origin_flag: '🇲🇦', destination_flag: '🇫🇷', carrier: 'FedEx Ground', tracking_number: '7489 5566 7788', status: 'Delayed', status_key: 'delayed', eta_label: '18:00', progress_percent: 45, updated_at: new Date().toISOString() },
        { id: 4, route: 'JFK → LAX', origin: 'New York', destination: 'Los Angeles', origin_flag: '🇺🇸', destination_flag: '🇺🇸', carrier: 'FedEx Express', tracking_number: '7489 9900 1122', status: 'In Transit', status_key: 'in_transit', eta_label: '22:15', progress_percent: 72, updated_at: new Date().toISOString() },
        { id: 5, route: 'DXB → SIN', origin: 'Dubai', destination: 'Singapore', origin_flag: '🇦🇪', destination_flag: '🇸🇬', carrier: 'FedEx Express', tracking_number: '7489 3344 5566', status: 'In Transit', status_key: 'in_transit', eta_label: '06:45', progress_percent: 55, updated_at: new Date().toISOString() },
      ],
      recent_conversations: [],
      system_health: [],
      user_roles: [],
      pending_invitations: 0,
      recent_users: [],
      fedex_metrics: { requests_today: 0, success_rate: 99, latency_ms: 120, error_rate: 0, requests_series: [] },
      activity_timeline: [],
      open_incidents: 0,
      notification_count: 0,
      total_users: 0,
    };
  }
}
