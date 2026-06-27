import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { EmployeeDocumentItem, EmployeePortalService } from '../../../../core/services/employee-portal.service';

@Component({
  selector: 'app-employee-documents-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-documents-page.component.html',
  styleUrls: ['../../employee-workspace.scss'],
})
export class EmployeeDocumentsPageComponent implements OnInit {
  items: EmployeeDocumentItem[] = [];
  q = '';
  type = 'all';

  constructor(private readonly employee: EmployeePortalService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const params: Record<string, string> = {};
    if (this.q) params['q'] = this.q;
    if (this.type !== 'all') params['type'] = this.type;
    this.employee.listDocuments(params).subscribe({ next: (items) => (this.items = items) });
  }

  preview(doc: EmployeeDocumentItem): void {
    this.employee.previewClientDocument(doc, () => window.alert('Impossible d\'ouvrir ce document.'));
  }

  download(doc: EmployeeDocumentItem): void {
    this.employee.downloadClientDocument(doc, () => window.alert('Impossible de télécharger ce document.'));
  }
}
