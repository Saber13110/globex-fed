import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, inject } from '@angular/core';

import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { ShipmentSummary } from '../../../../core/services/chatbot.service';
import { HistoryItem } from '../../../../core/services/history.service';
import { TrackingEvent } from '../../../../core/services/tracking.service';
import { ShipmentCardComponent } from '../../../../shared/components/shipment-card/shipment-card.component';

export type DrawerStatusBadge = 'delivered' | 'in_transit' | 'exception' | 'ready';

@Component({
  selector: 'app-history-detail-drawer',
  standalone: true,
  imports: [CommonModule, TranslatePipe, ShipmentCardComponent],
  templateUrl: './history-detail-drawer.component.html',
  styleUrl: './history-detail-drawer.component.scss',
})
export class HistoryDetailDrawerComponent {
  private readonly i18n = inject(I18nService);

  @Input({ required: true }) item!: HistoryItem;
  @Input() shipment: ShipmentSummary | null = null;
  @Input() loading = false;
  @Input() error: string | null = null;

  @Output() close = new EventEmitter<void>();
  @Output() openConversation = new EventEmitter<void>();

  eventsOpen = false;
  timelineShowAll = false;

  private readonly timelinePreviewCount = 5;

  get events(): TrackingEvent[] {
    return this.shipment?.events ?? [];
  }

  get tableEventRows(): Array<TrackingEvent & { dateLabel: string; timeLabel: string }> {
    return this.events.map((ev) => {
      const parts = this.formatEventTableParts(ev.at);
      return { ...ev, dateLabel: parts.date, timeLabel: parts.time };
    });
  }

  get visibleTimelineEvents(): TrackingEvent[] {
    if (this.timelineShowAll || this.events.length <= this.timelinePreviewCount) {
      return this.events;
    }
    return this.events.slice(0, this.timelinePreviewCount);
  }

  get hasMoreTimelineEvents(): boolean {
    return this.events.length > this.timelinePreviewCount && !this.timelineShowAll;
  }

  get statusBadge(): DrawerStatusBadge {
    const status = (this.displayStatus ?? '').toLowerCase();
    if (/deliver|livré|livre/.test(status)) return 'delivered';
    if (/exception|delay|retard|hold|problem|incident|failed|échec/.test(status)) return 'exception';
    if (/ready for pickup|pickup|disponible|prêt/.test(status)) return 'ready';
    return 'in_transit';
  }

  get displayStatus(): string {
    return this.shipment?.status ?? this.item.status ?? '—';
  }

  get displayLocation(): string {
    const loc = this.shipment?.current_location ?? this.item.current_location ?? '—';
    return loc.split(',')[0]?.trim() || loc;
  }

  get displayLocationFull(): string {
    return this.shipment?.current_location ?? this.item.current_location ?? '—';
  }

  get displayEta(): string {
    return this.shipment?.estimated_delivery ?? this.item.estimated_delivery ?? 'N/A';
  }

  get statusBadgeLabel(): string {
    const keys: Record<DrawerStatusBadge, string> = {
      delivered: 'history.badgeDelivered',
      in_transit: 'history.badgeInTransit',
      exception: 'history.badgeException',
      ready: 'history.badgeReady',
    };
    return this.i18n.t(keys[this.statusBadge]);
  }

  get eventsDetailsLabel(): string {
    return this.i18n.t('history.eventsDetailsCount', { count: String(this.events.length) });
  }

  onBackdropClick(event: MouseEvent): void {
    if ((event.target as HTMLElement).classList.contains('history-drawer__backdrop')) {
      this.close.emit();
    }
  }

  toggleEvents(): void {
    this.eventsOpen = !this.eventsOpen;
  }

  showAllTimelineEvents(): void {
    this.timelineShowAll = true;
  }

  formatLastUpdate(iso: string): string {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return iso;
    }
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((startToday.getTime() - startDate.getTime()) / 86_400_000);
    const locale = this.i18n.langCode() === 'en' ? 'en-US' : this.i18n.langCode() === 'ar' ? 'ar' : 'fr-FR';
    const time = date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 0) {
      return `${this.i18n.t('history.today')} · ${time}`;
    }
    if (diffDays === 1) {
      return `${this.i18n.t('sidebar.group.yesterday')} · ${time}`;
    }
    const day = date.toLocaleDateString(locale, { day: '2-digit', month: 'short', year: 'numeric' });
    return `${day} · ${time}`;
  }

  formatEventLine(iso: string): string {
    if (!iso?.trim()) {
      return '—';
    }
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return iso;
    }
    const locale = this.i18n.langCode() === 'en' ? 'en-US' : this.i18n.langCode() === 'ar' ? 'ar' : 'fr-FR';
    const date = d.toLocaleDateString(locale, { day: '2-digit', month: 'short', year: 'numeric' });
    const time = d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    return `${date} · ${time}`;
  }

  formatEventTableParts(iso: string): { date: string; time: string } {
    if (!iso?.trim()) {
      return { date: '—', time: '' };
    }
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return { date: iso, time: '' };
    }
    const locale = this.i18n.langCode() === 'en' ? 'en-US' : this.i18n.langCode() === 'ar' ? 'ar' : 'fr-FR';
    return {
      date: d.toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' }),
      time: d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }),
    };
  }

  eventTitle(description: string): string {
    return description?.trim() || '—';
  }

  eventLocation(location: string): string {
    return location?.trim() || '—';
  }
}
