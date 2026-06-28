import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import { TranslatePipe } from '../../../../../core/i18n/translate.pipe';
import { EmployeeClientOpsStats } from '../../../../../core/services/employee-portal.service';

@Component({
  selector: 'app-client-stats',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  templateUrl: './client-stats.component.html',
  styleUrl: './client-stats.component.scss',
})
export class ClientStatsComponent {
  @Input({ required: true }) stats!: EmployeeClientOpsStats;

  metricLabel(key: string): string {
    const map: Record<string, string> = {
      total_clients: 'employee.clientOps.metricTotalClients',
      active_clients: 'employee.clientOps.metricActiveClients',
      open_tickets: 'employee.clientOps.metricOpenTickets',
      active_shipments: 'employee.clientOps.metricActiveShipments',
      recent_documents: 'employee.clientOps.metricRecentDocuments',
      pending_issues: 'employee.clientOps.metricPendingIssues',
    };
    return map[key] ?? key;
  }
}
