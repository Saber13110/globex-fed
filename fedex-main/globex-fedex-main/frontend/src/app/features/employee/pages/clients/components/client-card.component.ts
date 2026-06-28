import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TranslatePipe } from '../../../../../core/i18n/translate.pipe';
import { EmployeeClientSummary } from '../../../../../core/services/employee-portal.service';

@Component({
  selector: 'app-client-card',
  standalone: true,
  imports: [CommonModule, RouterLink, TranslatePipe],
  templateUrl: './client-card.component.html',
  styleUrl: './client-card.component.scss',
})
export class ClientCardComponent {
  @Input({ required: true }) client!: EmployeeClientSummary;

  statusClass(status: string): string {
    const s = (status || 'active').toLowerCase();
    return `client-ops-card__status--${s}`;
  }
}
