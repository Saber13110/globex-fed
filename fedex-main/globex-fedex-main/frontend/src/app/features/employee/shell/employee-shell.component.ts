import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { Subscription, filter } from 'rxjs';

import { AuthService } from '../../../core/services/auth.service';
import {
  EmployeeSettingsTab,
  EmployeeShellPanelService,
} from '../../../core/services/employee-shell-panel.service';
import { EmployeeAiAgentFabComponent } from '../components/employee-ai-agent-fab.component';
import { EmployeeHelpPanelComponent } from '../components/employee-help-panel.component';
import { EmployeeSidebarComponent } from '../components/employee-sidebar.component';
import { EmployeeSettingsPanelComponent } from '../components/employee-settings-panel.component';
import { EmployeeTopbarComponent } from '../components/employee-topbar.component';

@Component({
  selector: 'app-employee-shell',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    EmployeeSidebarComponent,
    EmployeeTopbarComponent,
    EmployeeSettingsPanelComponent,
    EmployeeHelpPanelComponent,
    EmployeeAiAgentFabComponent,
  ],
  templateUrl: './employee-shell.component.html',
  styleUrls: ['../employee-workspace.scss', './employee-shell.component.scss'],
})
export class EmployeeShellComponent implements OnInit, OnDestroy {
  accountName = '';
  accountEmail = '';
  avatarInitial = 'E';
  settingsOpen = false;
  helpOpen = false;
  settingsTab: EmployeeSettingsTab = 'profile';

  private panelSub?: Subscription;
  private routerSub?: Subscription;

  constructor(
    private readonly auth: AuthService,
    private readonly router: Router,
    private readonly panels: EmployeeShellPanelService,
  ) {}

  ngOnInit(): void {
    this.auth.me().subscribe({
      next: (p) => {
        this.accountName = p.full_name;
        this.accountEmail = p.email;
        this.avatarInitial = this.initials(p.full_name);
      },
    });

    this.panelSub = new Subscription();
    this.panelSub.add(
      this.panels.onOpenSettings().subscribe((tab) => this.openSettings(tab)),
    );
    this.panelSub.add(this.panels.onOpenHelp().subscribe(() => this.openHelp()));

    this.routerSub = this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe(() => this.handleQueryPanels());

    this.handleQueryPanels();
  }

  ngOnDestroy(): void {
    this.panelSub?.unsubscribe();
    this.routerSub?.unsubscribe();
  }

  openSettings(tab: EmployeeSettingsTab = 'profile'): void {
    this.helpOpen = false;
    this.settingsTab = tab;
    this.settingsOpen = true;
  }

  openProfile(): void {
    this.openSettings('profile');
  }

  openHelp(): void {
    this.settingsOpen = false;
    this.helpOpen = true;
  }

  closeSettings(): void {
    this.settingsOpen = false;
  }

  closeHelp(): void {
    this.helpOpen = false;
  }

  logout(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/employee/login');
  }

  private handleQueryPanels(): void {
    const tree = this.router.parseUrl(this.router.url);
    const panel = tree.queryParams['panel'];
    const tab = tree.queryParams['tab'] as EmployeeSettingsTab | undefined;
    if (panel === 'settings') {
      this.openSettings(tab && ['profile', 'security', 'appearance', 'language'].includes(tab) ? tab : 'profile');
    } else if (panel === 'help') {
      this.openHelp();
    }
  }

  private initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'E';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
}
