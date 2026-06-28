import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { Subscription, filter } from 'rxjs';

import { TranslatePipe } from '../../../core/i18n/translate.pipe';

@Component({
  selector: 'app-employee-ai-agent-fab',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  templateUrl: './employee-ai-agent-fab.component.html',
  styleUrl: './employee-ai-agent-fab.component.scss',
})
export class EmployeeAiAgentFabComponent implements OnInit, OnDestroy {
  private readonly router = inject(Router);
  private sub?: Subscription;

  visible = true;
  readonly aiAvailable = true;

  ngOnInit(): void {
    this.updateVisible();
    this.sub = this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => this.updateVisible());
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  openAgent(): void {
    void this.router.navigate(['/employee/ai-agent']);
  }

  private updateVisible(): void {
    const url = this.router.url.split('?')[0];
    this.visible = !url.startsWith('/employee/ai-agent');
  }
}
