import { CommonModule } from '@angular/common';
import { Component, EventEmitter, HostListener, Output } from '@angular/core';

import { TranslatePipe } from '../../../core/i18n/translate.pipe';
import { EmployeeHelpPageComponent } from '../pages/help/employee-help-page.component';

@Component({
  selector: 'app-employee-help-panel',
  standalone: true,
  imports: [CommonModule, TranslatePipe, EmployeeHelpPageComponent],
  templateUrl: './employee-help-panel.component.html',
  styleUrls: ['./employee-settings-panel.component.scss', './employee-help-panel.component.scss'],
})
export class EmployeeHelpPanelComponent {
  @Output() closed = new EventEmitter<void>();

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.close();
  }

  close(): void {
    this.closed.emit();
  }
}
