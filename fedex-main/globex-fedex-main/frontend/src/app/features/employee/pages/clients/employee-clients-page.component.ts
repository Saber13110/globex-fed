import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged, EMPTY, switchMap, takeUntil } from 'rxjs';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import {
  EmployeeClientOpsStats,
  EmployeeClientSummary,
  EmployeePortalService,
  EmployeeSearchHit,
} from '../../../../core/services/employee-portal.service';
import { ClientCardComponent } from './components/client-card.component';
import { ClientSearchComponent } from './components/client-search.component';
import { ClientStatsComponent } from './components/client-stats.component';

@Component({
  selector: 'app-employee-clients-page',
  standalone: true,
  imports: [CommonModule, TranslatePipe, ClientStatsComponent, ClientSearchComponent, ClientCardComponent],
  templateUrl: './employee-clients-page.component.html',
  styleUrl: './employee-clients-page.component.scss',
})
export class EmployeeClientsPageComponent implements OnInit, OnDestroy {
  clients: EmployeeClientSummary[] = [];
  stats: EmployeeClientOpsStats | null = null;
  searchHits: EmployeeSearchHit[] = [];
  q = '';
  status = 'all';
  activity = '';
  loading = true;
  searching = false;
  showSearchResults = false;
  page = 1;
  pageSize = 12;
  total = 0;

  readonly heroBanner = 'assets/employee/hero-client-ops-v3.png';

  private readonly destroy$ = new Subject<void>();
  private readonly search$ = new Subject<string>();

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly router: Router,
  ) {}

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.total / this.pageSize));
  }

  ngOnInit(): void {
    this.loadStats();
    this.loadClients();

    this.search$
      .pipe(
        debounceTime(320),
        distinctUntilChanged(),
        switchMap((term) => {
          const trimmed = term.trim();
          if (trimmed.length < 2) {
            this.searchHits = [];
            this.showSearchResults = false;
            this.searching = false;
            return EMPTY;
          }
          this.searching = true;
          return this.employee.search(trimmed);
        }),
        takeUntil(this.destroy$),
      )
      .subscribe({
        next: (res) => {
          this.searchHits = res.items;
          this.showSearchResults = this.q.trim().length >= 2;
          this.searching = false;
        },
        error: () => {
          this.searching = false;
        },
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadStats(): void {
    this.employee.getClientOpsStats().subscribe({ next: (s) => (this.stats = s) });
  }

  loadClients(): void {
    this.loading = true;
    const params: Record<string, string> = {
      page: String(this.page),
      limit: String(this.pageSize),
    };
    if (this.q.trim()) params['q'] = this.q.trim();
    if (this.status !== 'all') params['status'] = this.status;
    if (this.activity) params['activity'] = this.activity;
    this.employee.listClients(params).subscribe({
      next: (r) => {
        this.clients = r.items;
        this.total = r.total;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  onSearchInput(): void {
    this.search$.next(this.q);
    this.page = 1;
    if (this.q.trim().length >= 2) {
      this.loadClients();
    }
  }

  applyFilters(): void {
    this.showSearchResults = false;
    this.page = 1;
    this.loadClients();
  }

  clearSearch(): void {
    this.q = '';
    this.searchHits = [];
    this.showSearchResults = false;
    this.page = 1;
    this.loadClients();
  }

  goToPage(p: number): void {
    if (p < 1 || p > this.totalPages) return;
    this.page = p;
    this.loadClients();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  openSearchHit(hit: EmployeeSearchHit): void {
    this.showSearchResults = false;
    void this.router.navigateByUrl(hit.link);
  }
}
