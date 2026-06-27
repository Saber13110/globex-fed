import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { HistoryService } from '../../core/services/history.service';
import { ChatSessionService } from '../../core/services/chat-session.service';
import { NotificationsService } from '../../core/services/notifications.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'app-user-space',
  standalone: true,
  imports: [CommonModule, RouterLink, TranslatePipe],
  templateUrl: './user-space-page.component.html',
  styleUrl: './user-space-page.component.scss',
})
export class UserSpacePageComponent implements OnInit {
  accountName = '';
  accountEmail = '';
  userRole = '';
  loading = true;

  trackedCount = 0;
  deliveredCount = 0;
  inTransitCount = 0;
  sessionsCount = 0;
  unreadNotifications = 0;

  constructor(
    private readonly auth: AuthService,
    private readonly history: HistoryService,
    private readonly sessions: ChatSessionService,
    private readonly notifications: NotificationsService,
    private readonly i18n: I18nService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    if (!this.auth.token()) {
      void this.router.navigateByUrl('/login');
      return;
    }
    this.auth.me().subscribe({
      next: (profile) => {
        this.accountName = profile.full_name;
        this.accountEmail = profile.email;
        this.userRole = profile.role;
      },
    });
    this.loadStats();
  }

  get accountAvatarInitial(): string {
    const v = (this.accountName || 'U').trim();
    return v ? v.charAt(0).toUpperCase() : 'U';
  }

  get accountAvatarClass(): string {
    return 'sidebar__avatar--variant-3';
  }

  get accountLanguage(): string {
    return this.i18n.uiLanguageLabel();
  }

  get colorMode(): 'light' | 'dark' | 'auto' {
    return 'light';
  }

  private loadStats(): void {
    this.loading = true;
    let pending = 3;
    const done = () => {
      pending -= 1;
      if (pending <= 0) {
        this.loading = false;
      }
    };
    this.history.list(200).subscribe({
      next: (rows) => {
        this.trackedCount = rows.length;
        this.deliveredCount = rows.filter((r) => (r.status || '').toLowerCase().includes('deliver')).length;
        this.inTransitCount = rows.filter((r) => {
          const s = (r.status || '').toLowerCase();
          return s.includes('transit') || s.includes('route') || s.includes('cours');
        }).length;
      },
      error: () => done(),
      complete: () => done(),
    });
    this.sessions.list({ limit: 500 }).subscribe({
      next: (list) => {
        this.sessionsCount = list.filter((s) => !s.is_archived).length;
      },
      error: () => done(),
      complete: () => done(),
    });
    this.notifications.getUnreadCount().subscribe({
      next: (res) => {
        this.unreadNotifications = res.count ?? 0;
      },
      error: () => done(),
      complete: () => done(),
    });
  }

  goChat(): void {
    void this.router.navigateByUrl('/chat');
  }

  logout(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/login');
  }
}
