import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { TranslatePipe } from '../../../../../core/i18n/translate.pipe';
import { EmployeeSearchHit } from '../../../../../core/services/employee-portal.service';

@Component({
  selector: 'app-client-search',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe],
  templateUrl: './client-search.component.html',
  styleUrl: './client-search.component.scss',
})
export class ClientSearchComponent {
  @Input() q = '';
  @Input() status = 'all';
  @Input() activity = '';
  @Input() searching = false;
  @Input() showSearchResults = false;
  @Input() searchHits: EmployeeSearchHit[] = [];

  @Output() qChange = new EventEmitter<string>();
  @Output() statusChange = new EventEmitter<string>();
  @Output() activityChange = new EventEmitter<string>();
  @Output() searchInput = new EventEmitter<void>();
  @Output() applyFilters = new EventEmitter<void>();
  @Output() clearSearch = new EventEmitter<void>();
  @Output() openHit = new EventEmitter<EmployeeSearchHit>();

  onQInput(value: string): void {
    this.qChange.emit(value);
    this.searchInput.emit();
  }

  searchKindLabel(kind: string): string {
    const map: Record<string, string> = {
      client: 'employee.clientOps.kindClient',
      tracking: 'employee.clientOps.kindTracking',
      ticket: 'employee.clientOps.kindTicket',
      document: 'employee.clientOps.kindDocument',
      notification: 'employee.clientOps.kindNotification',
    };
    return map[kind] ?? kind;
  }
}
