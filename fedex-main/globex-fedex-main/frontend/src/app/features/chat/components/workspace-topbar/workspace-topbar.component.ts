import { CommonModule } from '@angular/common';
import { Component, EventEmitter, HostListener, Input, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import {
  UserNotification,
  UserNotificationsService,
} from '../../../../core/services/user-notifications.service';

@Component({
  selector: 'app-workspace-topbar',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  templateUrl: './workspace-topbar.component.html',
  styleUrl: './workspace-topbar.component.scss',
})
export class WorkspaceTopbarComponent implements OnInit, OnDestroy {
  private readonly notifApi = inject(UserNotificationsService);
  private readonly router = inject(Router);
  private subs = new Subscription();

  @Input() accountName = '';
  @Input() avatarInitial = 'A';
  @Input() avatarClass = '';

  @Output() logout = new EventEmitter<void>();
  @Output() unreadChange = new EventEmitter<number>();

  unreadCount = 0;
  hasFreshNotif = false;
  notificationsOpen = false;
  notifications: UserNotification[] = [];
  loadingNotifications = false;

  ngOnInit(): void {
    this.notifApi.startPolling(12_000);
    this.subs.add(
      this.notifApi.unread$.subscribe((count) => {
        this.unreadCount = count;
        this.unreadChange.emit(count);
      }),
    );
    this.subs.add(this.notifApi.freshPulse$.subscribe((pulse) => (this.hasFreshNotif = pulse)));
    if (this.notifApi.unreadCount === 0) {
      this.notifApi.refreshUnread();
    } else {
      this.unreadCount = this.notifApi.unreadCount;
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.notifApi.stopPolling();
  }

  @HostListener('document:click', ['$event'])
  closeOnOutsideClick(event: MouseEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('.ux-topbar__notif-wrap, .ux-topbar__icon-btn')) {
      return;
    }
    this.notificationsOpen = false;
  }

  toggleNotifications(event: Event): void {
    event.stopPropagation();
    this.notificationsOpen = !this.notificationsOpen;
    if (this.notificationsOpen) {
      this.loadNotifications();
    }
  }

  onLogout(event: Event): void {
    event.stopPropagation();
    this.logout.emit();
  }

  openNotificationItem(item: UserNotification, event: Event): void {
    event.stopPropagation();
    if (!item.is_read) {
      this.notifApi.markRead(item.id).subscribe({
        next: () => {
          item.is_read = true;
          item.status = 'read';
          const next = Math.max(0, this.unreadCount - 1);
          this.notifApi.setUnreadCount(next);
        },
      });
    }
    this.notificationsOpen = false;
    const query: Record<string, number> = { notif: item.id };
    if (item.related_ticket_id) query['ticket'] = item.related_ticket_id;
    void this.router.navigate(['/notifications'], { queryParams: query });
  }

  markAllRead(event: Event): void {
    event.stopPropagation();
    this.notifApi.markAllRead().subscribe({
      next: () => {
        this.notifications.forEach((n) => {
          n.is_read = true;
          n.status = 'read';
        });
        this.notifApi.setUnreadCount(0);
      },
    });
  }

  viewAll(event: Event): void {
    event.stopPropagation();
    this.notificationsOpen = false;
    void this.router.navigateByUrl('/notifications');
  }

  private loadNotifications(): void {
    this.loadingNotifications = true;
    this.notifApi.list({ limit: 5 }).subscribe({
      next: (res) => {
        this.notifications = res.items;
        this.notifApi.setUnreadCount(res.unread_count);
        this.loadingNotifications = false;
      },
      error: () => {
        this.loadingNotifications = false;
        this.notifications = [];
      },
    });
  }
}
