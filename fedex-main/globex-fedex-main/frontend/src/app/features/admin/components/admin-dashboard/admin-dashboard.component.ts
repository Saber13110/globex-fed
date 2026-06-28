import { CommonModule } from '@angular/common';
import { Component, EventEmitter, HostBinding, Input, OnDestroy, OnInit, Output, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NgxChartsModule } from '@swimlane/ngx-charts';
import { Color, ScaleType } from '@swimlane/ngx-charts';
import { curveMonotoneX } from 'd3-shape';
import { HttpErrorResponse } from '@angular/common/http';

import {
  ActivityTimelineItem,
  CommandCenterPayload,
  CommandCenterService,
  DashboardNavEvent,
  ExecutiveInsight,
  KpiCardData,
  LiveShipmentItem,
  RecentConversationItem,
  SystemHealthItem,
  UserRoleSlice,
} from '../../../../core/services/command-center.service';
import { resolveShipmentFlag, flagImageUrl as shipmentFlagImageUrl } from '../../../../core/utils/country-flags.util';
import { AdminAiService } from '../../../../core/services/admin-ai.service';
import { AuthService } from '../../../../core/services/auth.service';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, NgxChartsModule],
  templateUrl: './admin-dashboard.component.html',
  styleUrl: './admin-dashboard.component.scss',
})
export class AdminDashboardComponent implements OnInit, OnDestroy {
  @Input() adminName = 'Administrator Globex';
  @Input() fitViewport = false;
  @Output() navigate = new EventEmitter<DashboardNavEvent>();
  @Output() manageUsers = new EventEmitter<void>();

  @HostBinding('class.gx-dash-host--fit')
  get hostFitClass(): boolean {
    return this.fitViewport;
  }

  @HostBinding('class.gx-dash-host--scroll')
  get hostScrollClass(): boolean {
    return !this.fitViewport;
  }

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly data = signal<CommandCenterPayload | null>(null);

  readonly aiQuery = signal('');
  readonly aiLoading = signal(false);
  readonly aiReply = signal<string | null>(null);
  readonly aiError = signal<string | null>(null);
  readonly adminRole = signal('admin');

  readonly aiBrain = 'assets/admin/ai-brain.png?v=6';
  readonly aiBrainWebp = 'assets/admin/ai-brain.webp?v=1';
  readonly heroBackground = 'assets/admin/hero-bg.png?v=2';
  readonly donutView: [number, number] = [160, 160];
  readonly miniDonutView: [number, number] = [88, 88];

  get chartView(): [number, number] {
    return this.fitViewport ? [120, 120] : this.donutView;
  }

  get miniChartView(): [number, number] {
    return this.fitViewport ? [72, 72] : this.miniDonutView;
  }

  readonly curve = curveMonotoneX;
  readonly fedexChart = signal<{ name: string; value: number }[]>([]);
  readonly roleChart = signal<{ name: string; value: number }[]>([]);
  readonly roleBadge = computed(() => {
    const map: Record<string, string> = {
      admin: 'SUPER ADMIN',
      employe: 'EMPLOYEE',
      client: 'CLIENT',
      manager: 'MANAGER',
    };
    return map[this.adminRole()] ?? 'ADMIN';
  });

  readonly fedexLineResults = computed(() => [
    { name: 'Requests', series: this.fedexChart().map((p) => ({ name: p.name, value: p.value })) },
  ]);

  readonly shipmentStatusFilter = signal<string | null>(null);

  readonly shipmentStatusChart = computed(() => {
    const items = this.data()?.live_shipments ?? [];
    const counts = { in_transit: 0, delivered: 0, delayed: 0 };
    for (const s of items) {
      if (s.status_key in counts) counts[s.status_key as keyof typeof counts]++;
      else counts.in_transit++;
    }
    return [
      { name: 'In Transit', value: counts.in_transit },
      { name: 'Delivered', value: counts.delivered },
      { name: 'Delayed', value: counts.delayed },
    ].filter((x) => x.value > 0);
  });

  readonly shipmentStatusLegend = computed(() => {
    const items = this.data()?.live_shipments ?? [];
    const meta = [
      { key: 'in_transit', label: 'In Transit', color: '#7C3AED' },
      { key: 'delivered', label: 'Delivered', color: '#22C55E' },
      { key: 'delayed', label: 'Delayed', color: '#FF6A00' },
    ];
    return meta
      .map((m) => ({ ...m, count: items.filter((s) => s.status_key === m.key).length }))
      .filter((m) => m.count > 0);
  });

  readonly displayedShipments = computed(() => {
    const items = this.data()?.live_shipments ?? [];
    const filter = this.shipmentStatusFilter();
    const filtered = filter ? items.filter((s) => s.status_key === filter) : items;
    return filtered.slice(0, 5);
  });

  readonly globalHealthScore = computed(() => {
    const items = this.systemHealthItems().filter((h) => h.operational);
    if (!items.length) return 0;
    const avg = items.reduce((s, h) => s + h.percent, 0) / items.length;
    return Math.round(avg * 10) / 10;
  });

  readonly conversationStats = computed(() => {
    const convs = this.data()?.recent_conversations ?? [];
    const high = convs.filter((c) => c.priority === 'high' || c.priority === 'urgent').length;
    return { total: convs.length, high, medium: Math.max(convs.length - high, 0) };
  });

  readonly conversationPriorityChart = computed(() => {
    const { high, medium } = this.conversationStats();
    return [
      { name: 'High', value: high },
      { name: 'Medium', value: medium },
    ].filter((x) => x.value > 0);
  });

  readonly activityLevelSegments = computed(() => {
    const items = this.data()?.activity_timeline ?? [];
    const palette: Record<string, string> = {
      INFO: '#3B82F6',
      SUCCESS: '#22C55E',
      WARNING: '#FF6A00',
      ERROR: '#EF4444',
    };
    const counts: Record<string, number> = {};
    for (const a of items) {
      const key = a.level.toUpperCase();
      counts[key] = (counts[key] ?? 0) + 1;
    }
    const total = Object.values(counts).reduce((s, v) => s + v, 0) || 1;
    return Object.entries(counts).map(([key, count]) => ({
      key,
      count,
      color: palette[key] ?? '#7C3AED',
      pct: Math.round((count / total) * 100),
    }));
  });

  readonly aiCommands = [
    { key: 'delays', label: 'Analyze shipment delays' },
    { key: 'exceptions', label: 'Top exceptions today' },
    { key: 'report', label: 'Generate performance report' },
    { key: 'activity', label: 'View user activity' },
  ];

  readonly quickActions = [
    { icon: 'plane', label: 'Track Shipment', action: 'tracking', tone: 'purple' },
    { icon: 'report', label: 'Generate Report', action: 'reports', tone: 'green' },
    { icon: 'alert', label: 'Create Incident', action: 'ai-assistant', tone: 'orange' },
    { icon: 'user-add', label: 'Add User', action: 'users', tone: 'blue' },
  ];

  lightScheme: Color = {
    name: 'globexEnterprise',
    selectable: false,
    group: ScaleType.Ordinal,
    domain: ['#7C3AED', '#FF6A00', '#3B82F6', '#8A5BFF'],
  };

  fedexLineScheme: Color = {
    name: 'fedexLine',
    selectable: false,
    group: ScaleType.Ordinal,
    domain: ['#7C3AED'],
  };

  shipmentStatusScheme: Color = {
    name: 'shipmentStatus',
    selectable: false,
    group: ScaleType.Ordinal,
    domain: ['#7C3AED', '#22C55E', '#FF6A00'],
  };

  priorityScheme: Color = {
    name: 'priority',
    selectable: false,
    group: ScaleType.Ordinal,
    domain: ['#FF6A00', '#7C3AED'],
  };

  private refreshTimer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly cc: CommandCenterService,
    private readonly ai: AdminAiService,
    private readonly auth: AuthService,
  ) {}

  ngOnInit(): void {
    this.auth.me().subscribe({
      next: (u) => {
        if (u.full_name) this.adminName = u.full_name;
        if (u.role) this.adminRole.set(u.role);
      },
    });
    this.load();
    this.refreshTimer = setInterval(() => this.load(false), 60_000);
  }

  ngOnDestroy(): void {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
  }

  load(showSpinner = true): void {
    if (showSpinner) this.loading.set(true);
    this.error.set(null);
    this.cc.getPayload().subscribe({
      next: (payload) => {
        this.data.set(payload);
        this.fedexChart.set(payload.fedex_metrics.requests_series.map((p) => ({ name: p.label, value: p.value })));
        this.roleChart.set(payload.user_roles.map((r) => ({ name: r.label, value: r.count })));
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Impossible de charger les données du tableau de bord.');
        this.loading.set(false);
      },
    });
  }

  kpiIconSrc(title: string): string {
    const t = title.toLowerCase();
    if (t.includes('shipment')) return 'assets/admin/kpi-shipments.png';
    if (t.includes('deliver')) return 'assets/admin/kpi-deliveries.png';
    if (t.includes('incident')) return 'assets/admin/kpi-incidents.png';
    if (t.includes('user')) return 'assets/admin/kpi-users.png';
    return 'assets/admin/kpi-shipments.png';
  }

  kpiCardClass(title: string): string {
    const t = title.toLowerCase();
    if (t.includes('incident')) return 'gx-kpi-card--warning';
    if (t.includes('user')) return 'gx-kpi-card--users';
    if (t.includes('deliver')) return 'gx-kpi-card--delivery';
    return 'gx-kpi-card--shipments';
  }

  kpiSparkColor(title: string): string {
    const t = title.toLowerCase();
    if (t.includes('incident')) return '#FF6A00';
    if (t.includes('user')) return '#3B82F6';
    return '#7C3AED';
  }

  sparkPoints(sparkline: number[], height = 28): string {
    if (!sparkline.length) return '';
    const w = 100;
    const h = height;
    const max = Math.max(...sparkline, 1);
    const step = w / Math.max(sparkline.length - 1, 1);
    return sparkline
      .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`)
      .join(' ');
  }

  sparkArea(sparkline: number[], height = 28): string {
    if (!sparkline.length) return '';
    const line = this.sparkPoints(sparkline, height);
    return `${line} L100,${height} L0,${height} Z`;
  }

  kpiSparkFill(title: string): string {
    return this.kpiSparkColor(title);
  }

  heroStats(): { label: string; value: number; icon: string }[] {
    const payload = this.data();
    if (!payload) return [];
    const fromApi = payload.hero_stats ?? [];
    if (fromApi.length >= 4) {
      const labels = ['Shipments Today', 'Deliveries Completed', 'Active Users', 'Open Incidents'];
      return fromApi.slice(0, 4).map((s, i) => ({
        label: labels[i] ?? s.label,
        value: s.value,
        icon: s.icon,
      }));
    }
    const kpis = payload.kpis ?? [];
    const labels = ['Shipments Today', 'Deliveries Completed', 'Active Users', 'Open Incidents'];
    return kpis.slice(0, 4).map((k, i) => ({
      label: labels[i] ?? k.title,
      value: k.value,
      icon: ['package', 'check', 'users', 'alert'][i] ?? 'package',
    }));
  }

  sendAi(quickAction?: string): void {
    const msg = this.aiQuery().trim();
    if (!msg && !quickAction) return;
    this.aiLoading.set(true);
    this.aiError.set(null);
    this.aiReply.set(null);
    this.ai.query(msg || 'Executive summary', quickAction).subscribe({
      next: (res) => {
        this.aiReply.set(res.reply);
        this.aiLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.aiError.set(typeof err.error?.detail === 'string' ? err.error.detail : 'IA indisponible.');
        this.aiLoading.set(false);
      },
    });
  }

  runCommand(key: string, label: string): void {
    this.aiQuery.set(label);
    this.sendAi(key);
  }

  kpiHeroLabel(title: string, index: number): string {
    const labels = ['Shipments Today', 'Deliveries Completed', 'Open Incidents', 'Active Users'];
    return labels[index] ?? title;
  }

  kpiHeroIcon(title: string): string {
    const t = title.toLowerCase();
    if (t.includes('incident')) return 'alert';
    if (t.includes('user')) return 'users';
    if (t.includes('deliver')) return 'check';
    return 'package';
  }

  executiveInsights(): ExecutiveInsight[] {
    return this.data()?.executive_insights ?? [];
  }

  insightIcon(icon: string): string {
    const map: Record<string, string> = {
      alert: 'shield',
      warning: 'package',
      check: 'shield-check',
      users: 'users',
      trend: 'chart',
    };
    return map[icon] ?? 'shield';
  }

  go(target: string, extra: Omit<DashboardNavEvent, 'target'> = {}): void {
    this.navigate.emit({ target, ...extra });
  }

  openShipment(shipment: LiveShipmentItem): void {
    this.go('tracking', {
      trackingNumber: shipment.tracking_number,
      shipmentId: shipment.id,
    });
  }

  openHealth(item: SystemHealthItem): void {
    const routes: Record<string, string> = {
      fedex: 'tracking',
      database: 'monitoring',
      ai: 'ai-assistant',
      notifications: 'settings',
      storage: 'settings',
      auth: 'audit-logs',
    };
    this.go(routes[item.key] ?? 'settings', { healthKey: item.key });
  }

  openConversation(conversation: RecentConversationItem): void {
    this.go('conversations', { conversationId: conversation.session_id });
  }

  openActivity(activity: ActivityTimelineItem): void {
    if (activity.category === 'security' || activity.level === 'WARNING' || activity.level === 'CRITICAL') {
      this.go('incidents');
      return;
    }
    this.go('audit-logs', { auditQuery: activity.message });
  }

  openRole(role: UserRoleSlice): void {
    const map: Record<string, DashboardNavEvent['roleKey']> = {
      client: 'client',
      employe: 'employe',
      employee: 'employe',
      admin: 'admin',
    };
    this.go('users', { roleKey: map[role.role_key] ?? 'all' });
  }

  openAiAssistant(prefill?: string): void {
    if (prefill) this.aiQuery.set(prefill);
    this.go('ai-assistant');
  }

  handleInsight(insight: ExecutiveInsight): void {
    const routes: Record<string, string> = {
      delays: 'tracking',
      incidents: 'incidents',
      api: 'reports',
      engagement: 'users',
      completion: 'reports',
    };
    const target = routes[insight.id] ?? 'ai-assistant';
    if (target === 'ai-assistant') {
      this.aiQuery.set(insight.message);
      this.sendAi(insight.id);
    }
    this.go(target);
  }

  viewFullReport(): void {
    this.go('reports');
  }

  quickNav(action: string): void {
    if (action === 'ai-assistant') {
      this.aiQuery.set('Rapport incident pour colis en retard');
      this.go('ai-assistant');
      return;
    }
    this.go(action);
  }

  quickActionCount(action: string): number | null {
    const d = this.data();
    if (!d) return null;
    switch (action) {
      case 'tracking':
        return d.live_shipments.length > 0 ? d.live_shipments.length : null;
      case 'ai-assistant':
        return d.open_incidents > 0 ? d.open_incidents : null;
      case 'users':
        return d.pending_invitations > 0 ? d.pending_invitations : null;
      default:
        return null;
    }
  }

  toggleShipmentFilter(key: string): void {
    this.shipmentStatusFilter.set(this.shipmentStatusFilter() === key ? null : key);
  }

  isShipmentFilterActive(key: string): boolean {
    return this.shipmentStatusFilter() === key;
  }

  healthBarClass(item: SystemHealthItem): string {
    return item.operational ? 'gx-health-bar__fill--ok' : 'gx-health-bar__fill--warn';
  }

  resolveFlag(flag: string, location: string): string {
    return resolveShipmentFlag(flag, location);
  }

  flagImg(flag: string, location: string): string | null {
    return shipmentFlagImageUrl(flag, location, 40);
  }

  systemHealthItems(): SystemHealthItem[] {
    return this.data()?.system_health ?? [];
  }

  dashboardHealthItems(): SystemHealthItem[] {
    return this.systemHealthItems().slice(0, 4);
  }

  statusClass(key: string): string {
    return `status--${key}`;
  }

  insightToneClass(tone: string): string {
    return `insight--${tone}`;
  }

  roleTotal(roles: UserRoleSlice[]): number {
    return roles.reduce((s, r) => s + r.count, 0) || 1;
  }

  rolePercent(role: UserRoleSlice, roles: UserRoleSlice[]): number {
    return Math.round((role.count / this.roleTotal(roles)) * 100);
  }

  timelineDotClass(level: string, message: string): string {
    const l = level.toUpperCase();
    const m = message.toLowerCase();
    if (l === 'ERROR' || m.includes('incident')) return 'tl-dot--red';
    if (l === 'WARNING' || m.includes('updated')) return 'tl-dot--orange';
    if (l === 'SUCCESS' || m.includes('login')) return 'tl-dot--green';
    if (m.includes('ai') || m.includes('report')) return 'tl-dot--purple';
    return 'tl-dot--blue';
  }

  priorityBadgeClass(priority: string): string {
    const p = priority.toLowerCase();
    if (p === 'high' || p === 'urgent') return 'gx-badge--high';
    if (p === 'medium') return 'gx-badge--medium';
    return 'gx-badge--low';
  }

  activityLetter(category: string): string {
    const c = (category || 'S').trim();
    return c.charAt(0).toUpperCase();
  }

  trackKpi(_: number, k: KpiCardData): string {
    return k.title;
  }
}
