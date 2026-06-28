import { animate, style, transition, trigger } from '@angular/animations';
import { CommonModule, DatePipe } from '@angular/common';
import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  ReportCatalogItem,
  ReportKpiItem,
  ReportRun,
  ReportsService,
} from '../../../../core/services/reports.service';

type ReportTab = 'all' | 'shipments' | 'performance' | 'exceptions' | 'finance' | 'custom';

@Component({
  selector: 'app-admin-reports',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe, MatSnackBarModule],
  templateUrl: './admin-reports.component.html',
  styleUrl: './admin-reports.component.scss',
  animations: [
    trigger('fadeIn', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(8px)' }),
        animate('240ms ease-out', style({ opacity: 1, transform: 'translateY(0)' })),
      ]),
    ]),
  ],
})
export class AdminReportsComponent implements OnInit {
  readonly tabs: { id: ReportTab; label: string }[] = [
    { id: 'all', label: 'All Reports' },
    { id: 'shipments', label: 'Shipments' },
    { id: 'performance', label: 'Performance' },
    { id: 'exceptions', label: 'Exceptions' },
    { id: 'finance', label: 'Finance' },
    { id: 'custom', label: 'Custom' },
  ];

  readonly loading = signal(true);
  readonly kpisLoading = signal(true);
  readonly generating = signal(false);
  readonly aiLoading = signal(false);

  readonly kpis = signal<ReportKpiItem[]>([]);
  readonly catalog = signal<ReportCatalogItem[]>([]);
  readonly recent = signal<ReportRun[]>([]);

  readonly activeTab = signal<ReportTab>('all');
  readonly search = signal('');
  readonly filtersOpen = signal(false);
  readonly categoryFilter = signal('all');
  readonly formatFilter = signal('all');
  readonly page = signal(1);
  readonly pageSize = signal(6);
  readonly total = signal(0);

  dateFrom = '';
  dateTo = '';
  aiPrompt = '';

  readonly aiExamples = [
    'Generate monthly logistics report',
    'Analyze shipment delays',
    'Export failed deliveries',
    'Create customer activity report',
  ];

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize())));

  constructor(
    private readonly api: ReportsService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnInit(): void {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    this.dateFrom = start.toISOString().slice(0, 10);
    this.dateTo = now.toISOString().slice(0, 10);
    this.reload();
  }

  reload(): void {
    this.loadKpis();
    this.loadList();
    this.api.getRecent().subscribe({
      next: (r) => this.recent.set(r.items),
      error: () => this.recent.set([]),
    });
    this.loading.set(false);
  }

  setTab(tab: ReportTab): void {
    this.activeTab.set(tab);
    this.page.set(1);
    this.loadList();
  }

  applyFilters(): void {
    this.page.set(1);
    this.loadKpis();
    this.loadList();
  }

  generateNew(): void {
    const slug = this.catalog()[0]?.slug ?? 'tracking-history';
    this.generateReport(slug, 'xlsx');
  }

  generateReport(slug: string, format: string): void {
    this.generating.set(true);
    this.api.generate(slug, format, this.dateFrom, this.dateTo).subscribe({
      next: (res) => {
        this.generating.set(false);
        this.toast('Rapport généré avec succès.', 'success');
        this.downloadRun(res.run);
        this.reload();
      },
      error: (err: HttpErrorResponse) => {
        this.generating.set(false);
        this.toast(this.err(err, 'Échec de la génération.'), 'error');
      },
    });
  }

  downloadRun(run: ReportRun): void {
    this.api.downloadRun(run.id, `${run.slug}.${run.format === 'xlsx' ? 'xlsx' : run.format}`);
  }

  previewCatalog(item: ReportCatalogItem): void {
    if (!item.last_run_id) {
      this.generateReport(item.slug, 'json');
      return;
    }
    this.api.previewRun(item.last_run_id).subscribe({
      next: (p) => {
        const preview = p.rows.slice(0, 5).map((r) => r.join(' | ')).join('\n');
        alert(`${item.name}\n\n${preview || 'Aperçu indisponible.'}\n\n(${p.total_rows} lignes)`);
      },
      error: () => this.toast('Aperçu indisponible.', 'error'),
    });
  }

  shareCatalog(item: ReportCatalogItem): void {
    if (!item.last_run_id) {
      this.toast('Générez le rapport avant de le partager.', 'error');
      return;
    }
    this.api.shareRun(item.last_run_id).subscribe({
      next: (r) => {
        const full = `${window.location.origin}${r.share_url}`;
        navigator.clipboard?.writeText(full);
        this.toast(r.message, 'success');
      },
      error: (err: HttpErrorResponse) => this.toast(this.err(err, 'Partage échoué.'), 'error'),
    });
  }

  deleteRun(run: ReportRun): void {
    if (!confirm(`Supprimer le rapport « ${run.name} » ?`)) return;
    this.api.deleteRun(run.id).subscribe({
      next: () => {
        this.toast('Rapport supprimé.', 'success');
        this.reload();
      },
      error: (err: HttpErrorResponse) => this.toast(this.err(err, 'Suppression échouée.'), 'error'),
    });
  }

  exportQuick(fmt: 'excel' | 'csv' | 'json' | 'pdf'): void {
    this.api.exportFormat(fmt, 'tracking-history', this.dateFrom, this.dateTo);
    this.toast(`Export ${fmt.toUpperCase()} lancé.`, 'success');
  }

  runAi(example?: string): void {
    const prompt = (example ?? this.aiPrompt).trim();
    if (prompt.length < 3) return;
    this.aiLoading.set(true);
    this.api.aiReport(prompt).subscribe({
      next: (r) => {
        this.aiLoading.set(false);
        this.aiPrompt = '';
        this.toast(r.reply.slice(0, 200) + (r.reply.length > 200 ? '…' : ''), 'success');
        if (r.run) this.downloadRun(r.run);
        this.reload();
      },
      error: (err: HttpErrorResponse) => {
        this.aiLoading.set(false);
        this.toast(this.err(err, 'IA indisponible.'), 'error');
      },
    });
  }

  sparkPath(values: number[]): string {
    if (!values.length) return '';
    const w = 72;
    const h = 28;
    const max = Math.max(...values, 1);
    const min = Math.min(...values);
    const range = max - min || 1;
    const pts = values.map((v, i) => {
      const x = (i / (values.length - 1 || 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    });
    return `M ${pts.join(' L ')}`;
  }

  categoryClass(cat: string): string {
    return `rpt-cat--${cat}`;
  }

  statusClass(st: string): string {
    return `rpt-status--${(st || 'completed').toLowerCase()}`;
  }

  formatClass(fmt: string): string {
    return `rpt-fmt--${(fmt || 'xlsx').toLowerCase()}`;
  }

  private loadKpis(): void {
    this.kpisLoading.set(true);
    this.api.getKpis(this.dateFrom, this.dateTo).subscribe({
      next: (r) => {
        this.kpis.set(r.items);
        this.kpisLoading.set(false);
      },
      error: () => this.kpisLoading.set(false),
    });
  }

  loadList(): void {
    this.api
      .listReports({
        tab: this.activeTab(),
        category: this.categoryFilter(),
        search: this.search(),
        format: this.formatFilter(),
        page: this.page(),
        page_size: this.pageSize(),
        date_from: this.dateFrom,
        date_to: this.dateTo,
      })
      .subscribe({
        next: (r) => {
          this.catalog.set(r.items);
          this.total.set(r.total);
          if (r.runs.length) this.recent.set(r.runs);
        },
        error: () => this.toast('Impossible de charger les rapports.', 'error'),
      });
  }

  private toast(msg: string, type: 'success' | 'error'): void {
    this.snack.open(msg, 'Fermer', {
      duration: 4500,
      panelClass: type === 'success' ? 'set-snack--ok' : 'set-snack--err',
      horizontalPosition: 'end',
      verticalPosition: 'top',
    });
  }

  private err(err: HttpErrorResponse, fallback: string): string {
    const d = err.error?.detail;
    return typeof d === 'string' ? d : fallback;
  }
}
