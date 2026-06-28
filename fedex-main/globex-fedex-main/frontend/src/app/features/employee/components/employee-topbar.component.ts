import { CommonModule } from '@angular/common';
import { Component, ElementRef, EventEmitter, HostListener, Input, OnDestroy, OnInit, Output, ViewChild, inject } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription, interval } from 'rxjs';

import { TranslatePipe } from '../../../core/i18n/translate.pipe';
import { EmployeeAdminCommsStateService } from '../../../core/services/employee-admin-comms-state.service';
import { EmployeeHelpdeskStateService } from '../../../core/services/employee-helpdesk-state.service';
import { EmployeeShellPanelService } from '../../../core/services/employee-shell-panel.service';
import { EmployeeNotification, EmployeePortalService } from '../../../core/services/employee-portal.service';

@Component({
  selector: 'app-employee-topbar',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  templateUrl: './employee-topbar.component.html',
  styleUrl: './employee-topbar.component.scss',
})
export class EmployeeTopbarComponent implements OnInit, OnDestroy {
  @ViewChild('notifBtn') notifBtn?: ElementRef<HTMLButtonElement>;

  private readonly employee = inject(EmployeePortalService);
  private readonly helpdeskState = inject(EmployeeHelpdeskStateService);
  private readonly commsState = inject(EmployeeAdminCommsStateService);
  private readonly router = inject(Router);
  private readonly panels = inject(EmployeeShellPanelService);
  private pollSub?: Subscription;
  private helpdeskSub?: Subscription;
  private commsSub?: Subscription;

  @Input() accountName = '';
  @Input() avatarInitial = 'E';

  @Output() logout = new EventEmitter<void>();

  unreadCount = 0;
  unreadTicketCount = 0;
  unreadAdminChatCount = 0;
  notificationsOpen = false;
  notifications: EmployeeNotification[] = [];
  loadingNotifications = false;
  notifPanelStyle: Record<string, string> = {};

  ngOnInit(): void {
    this.refreshUnread();
    this.pollSub = interval(15_000).subscribe(() => this.refreshUnread());
    this.helpdeskSub = this.helpdeskState.unreadTickets$.subscribe((count) => {
      this.unreadTicketCount = count;
    });
    this.employee.getHelpdeskStats().subscribe({
      next: (s) => this.helpdeskState.setUnread(s.unread),
    });
    this.commsSub = this.commsState.unreadAdminChat$.subscribe((count) => {
      this.unreadAdminChatCount = count;
    });
    this.employee.getAdminChat().subscribe({
      next: (res) => this.commsState.setUnread(res.unread_count),
    });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
    this.helpdeskSub?.unsubscribe();
    this.commsSub?.unsubscribe();
  }

  totalBellCount(): number {
    return this.unreadCount + this.unreadTicketCount + this.unreadAdminChatCount;
  }

  @HostListener('document:click', ['$event'])
  closeOnOutsideClick(event: MouseEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.emp-topbar__notif-wrap, .emp-topbar__icon-btn')) {
      return;
    }
    this.notificationsOpen = false;
  }

  toggleNotifications(event: Event): void {
    event.stopPropagation();
    this.notificationsOpen = !this.notificationsOpen;
    if (this.notificationsOpen) {
      this.updateNotifPanelPosition();
      this.loadNotifications();
    }
  }

  @HostListener('window:resize')
  @HostListener('window:scroll')
  onViewportChange(): void {
    if (this.notificationsOpen) {
      this.updateNotifPanelPosition();
    }
  }

  onLogout(event: Event): void {
    event.stopPropagation();
    this.logout.emit();
  }

  openNotificationItem(item: EmployeeNotification, event: Event): void {
    event.stopPropagation();
    if (!item.is_read) {
      this.employee.markNotificationRead(item.id).subscribe({
        next: () => {
          item.is_read = true;
          this.unreadCount = Math.max(0, this.unreadCount - 1);
        },
      });
    }
    this.notificationsOpen = false;
    const link = item.link || '/employee/notifications';
    if (link.includes('panel=settings')) {
      const tab = new URL(link, 'http://local').searchParams.get('tab');
      this.panels.requestSettings(
        tab === 'security' || tab === 'appearance' || tab === 'language' ? tab : 'profile',
      );
      return;
    }
    if (link.includes('panel=help')) {
      this.panels.requestHelp();
      return;
    }
    if (link.startsWith('/employee')) {
      void this.router.navigateByUrl(link);
      return;
    }
    void this.router.navigateByUrl('/employee/notifications');
  }

  viewAll(event: Event): void {
    event.stopPropagation();
    this.notificationsOpen = false;
    void this.router.navigateByUrl('/employee/notifications');
  }

  private refreshUnread(): void {
    this.employee.listNotifications({ limit: '1' }).subscribe({
      next: (res) => (this.unreadCount = res.unread_count),
    });
  }

  private loadNotifications(): void {
    this.loadingNotifications = true;
    this.employee.listNotifications({ limit: '5' }).subscribe({
      next: (res) => {
        this.notifications = res.items;
        this.unreadCount = res.unread_count;
        this.loadingNotifications = false;
        this.updateNotifPanelPosition();
      },
      error: () => {
        this.loadingNotifications = false;
        this.notifications = [];
      },
    });
  }

  private updateNotifPanelPosition(): void {
    const btn = this.notifBtn?.nativeElement;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    this.notifPanelStyle = {
      top: `${rect.bottom + 8}px`,
      right: `${Math.max(12, window.innerWidth - rect.right)}px`,
    };
  }
}
