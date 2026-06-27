import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { I18nService } from '../../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AuthService } from '../../../../core/services/auth.service';
import {
  EmployeeDashboardWorkspace,
  EmployeePortalService,
} from '../../../../core/services/employee-portal.service';

interface QuickAction {
  labelKey: string;
  descKey: string;
  route: string;
  icon: string;
}

const ADMIN_CLIENT_PATTERN = /admin/i;

@Component({
  selector: 'app-employee-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-dashboard.component.html',
  styleUrls: ['./employee-dashboard.component.scss', './employee-ai-command-center.scss'],
})
export class EmployeeDashboardComponent implements OnInit {
  accountName = '';
  employeeInitials = 'EM';
  workspace: EmployeeDashboardWorkspace | null = null;
  loading = true;
  aiDraft = '';
  readonly heroIllustration = 'assets/employee/ai-core-hero.png?v=7';

  readonly quickActions: QuickAction[] = [
    { labelKey: 'employee.ops.actionClientMgmt', descKey: 'employee.ops.actionClientMgmtDesc', route: '/employee/clients', icon: 'users' },
    { labelKey: 'employee.ops.actionTrackingOps', descKey: 'employee.ops.actionTrackingOpsDesc', route: '/employee/tracking', icon: 'package' },
    { labelKey: 'employee.ops.actionTicket', descKey: 'employee.ops.actionTicketDesc', route: '/employee/support', icon: 'ticket' },
    { labelKey: 'employee.ops.actionDocsCenter', descKey: 'employee.ops.actionDocsCenterDesc', route: '/employee/documents', icon: 'file' },
    { labelKey: 'employee.ops.actionAdmin', descKey: 'employee.ops.actionAdminDesc', route: '/employee/admin-chat', icon: 'message' },
    { labelKey: 'employee.ops.actionNotif', descKey: 'employee.ops.actionNotifDesc', route: '/employee/notifications', icon: 'bell' },
  ];

  constructor(
    private readonly auth: AuthService,
    private readonly employee: EmployeePortalService,
    private readonly i18n: I18nService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.auth.me().subscribe({
      next: (p) => {
        this.accountName = p.full_name;
        this.employeeInitials = this.initials(p.full_name);
      },
    });
    this.loadWorkspace();
  }

  loadWorkspace(): void {
    this.loading = true;
    this.employee.getDashboard().subscribe({
      next: (ws) => {
        this.workspace = ws;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  trackingEvents() {
    const events = this.workspace?.tracking_summary.latest_events ?? [];
    return events.filter((ev) => !ADMIN_CLIENT_PATTERN.test(ev.client_name || ''));
  }

  sendAi(): void {
    const q = this.aiDraft.trim();
    if (!q) return;
    void this.router.navigate(['/employee/ai-agent'], { queryParams: { q } });
  }

  timeAgo(iso: string): string {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return this.i18n.t('employee.ops.justNow');
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    return `${Math.floor(hours / 24)}d`;
  }

  priorityClass(priority: string): string {
    const p = (priority || 'medium').toLowerCase();
    if (p === 'high') return 'ops-priority--high';
    if (p === 'low') return 'ops-priority--low';
    return 'ops-priority--medium';
  }

  statusClass(status: string): string {
    return `ops-status--${(status || 'open').toLowerCase()}`;
  }

  shipmentStatusClass(status: string): string {
    const s = (status || '').toLowerCase();
    if (s.includes('pickup') || s.includes('ready')) return 'ops-ship-status--pickup';
    if (s.includes('transit') || s.includes('route')) return 'ops-ship-status--transit';
    if (s.includes('deliver')) return 'ops-ship-status--delivered';
    if (s.includes('exception') || s.includes('delay')) return 'ops-ship-status--exception';
    return 'ops-ship-status--default';
  }

  notifIcon(kind: string): string {
    if (kind.includes('support') || kind.includes('reply')) return 'ticket';
    if (kind.includes('tracking')) return 'package';
    if (kind.includes('document') || kind.includes('export')) return 'file';
    if (kind.includes('admin')) return 'message';
    return 'bell';
  }

  private initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'EM';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
}
