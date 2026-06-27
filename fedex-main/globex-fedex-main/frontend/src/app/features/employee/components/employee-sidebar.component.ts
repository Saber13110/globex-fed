import { CommonModule } from '@angular/common';

import { Component, ElementRef, EventEmitter, HostListener, Input, OnDestroy, OnInit, Output, ViewChild, inject } from '@angular/core';

import { NavigationEnd, Router, RouterLink, RouterLinkActive } from '@angular/router';

import { Subscription, filter } from 'rxjs';



import { TranslatePipe } from '../../../core/i18n/translate.pipe';

import { I18nService } from '../../../core/i18n/i18n.service';
import { LangCode } from '../../../core/i18n/i18n.types';
import { AuthService } from '../../../core/services/auth.service';
import { UserPreferencesService } from '../../../core/services/user-preferences.service';

import { EmployeeHelpdeskStateService } from '../../../core/services/employee-helpdesk-state.service';

import { EmployeeAdminCommsStateService } from '../../../core/services/employee-admin-comms-state.service';

import { EmployeeNotificationsStateService } from '../../../core/services/employee-notifications-state.service';
import { EmployeePortalService } from '../../../core/services/employee-portal.service';



interface SidebarItem {

  labelKey: string;

  route?: string;

  action?: 'profile' | 'settings' | 'help';

  icon: string;

  badgeKey?: 'adminChat' | 'support' | 'notifications';

}



interface SidebarSection {

  titleKey: string;

  items: SidebarItem[];

}



@Component({

  selector: 'app-employee-sidebar',

  standalone: true,

  imports: [CommonModule, RouterLink, RouterLinkActive, TranslatePipe],

  templateUrl: './employee-sidebar.component.html',

  styleUrl: './employee-sidebar.component.scss',

})

export class EmployeeSidebarComponent implements OnInit, OnDestroy {

  @Input() accountName = '';

  @Input() accountEmail = '';

  @Input() avatarInitial = 'E';



  @Output() openProfile = new EventEmitter<void>();

  @Output() openSettings = new EventEmitter<void>();

  @Output() openHelp = new EventEmitter<void>();

  @Output() logout = new EventEmitter<void>();

  @ViewChild('langTrigger') langTrigger?: ElementRef<HTMLButtonElement>;

  readonly i18n = inject(I18nService);

  collapsed = false;

  accountMenuOpen = false;

  langFlyoutOpen = false;

  langFlyoutTop = 0;

  langFlyoutLeft = 0;

  private langFlyoutCloseTimer: ReturnType<typeof setTimeout> | null = null;

  unreadAdminChat = 0;
  openTickets = 0;
  unreadTickets = 0;
  unreadNotifications = 0;
  notifFreshPulse = false;



  readonly sections: SidebarSection[] = [

    {

      titleKey: 'employee.sidebar.workspace',

      items: [

        { labelKey: 'employee.sidebar.home', route: '/employee', icon: 'home' },

        { labelKey: 'employee.sidebar.aiAssistant', route: '/employee/ai-assistant', icon: 'bot' },

      ],

    },

    {

      titleKey: 'employee.sidebar.operations',

      items: [

        { labelKey: 'employee.sidebar.clients', route: '/employee/clients', icon: 'users' },

        { labelKey: 'employee.sidebar.tracking', route: '/employee/tracking', icon: 'package' },

      ],

    },

    {

      titleKey: 'employee.sidebar.support',

      items: [

        { labelKey: 'employee.sidebar.tickets', route: '/employee/support', icon: 'ticket', badgeKey: 'support' },

        { labelKey: 'employee.sidebar.adminChat', route: '/employee/admin-chat', icon: 'message', badgeKey: 'adminChat' },

      ],

    },

    {

      titleKey: 'employee.sidebar.account',

      items: [

        { labelKey: 'employee.sidebar.notifications', route: '/employee/notifications', icon: 'bell', badgeKey: 'notifications' },

      ],

    },

  ];



  private sub?: Subscription;

  private helpdeskSub?: Subscription;

  private commsSub?: Subscription;

  private notifSub?: Subscription;

  private notifPulseSub?: Subscription;



  constructor(

    private readonly employee: EmployeePortalService,

    private readonly notifState: EmployeeNotificationsStateService,

    private readonly helpdeskState: EmployeeHelpdeskStateService,

    private readonly commsState: EmployeeAdminCommsStateService,

    private readonly auth: AuthService,

    private readonly prefs: UserPreferencesService,

    private readonly router: Router,

  ) {}



  ngOnInit(): void {

    this.refreshBadges();

    this.helpdeskSub = this.helpdeskState.unreadTickets$.subscribe((count) => (this.unreadTickets = count));

    this.commsSub = this.commsState.unreadAdminChat$.subscribe((count) => (this.unreadAdminChat = count));

    this.sub = this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {

      this.refreshBadges();

    });

  }



  ngOnDestroy(): void {

    this.sub?.unsubscribe();

    this.helpdeskSub?.unsubscribe();

    this.commsSub?.unsubscribe();

    this.notifSub?.unsubscribe();

    this.notifPulseSub?.unsubscribe();

    this.notifState.stopPolling();

  }



  @HostListener('document:click', ['$event'])

  closeOnOutsideClick(event: MouseEvent): void {

    const target = event.target as HTMLElement | null;

    if (target?.closest('.emp-sidebar__account-wrap, .emp-sidebar__lang-flyout')) {

      return;

    }

    this.accountMenuOpen = false;

    this.closeLangFlyout();

  }



  @HostListener('window:resize')

  onWindowResize(): void {

    if (this.langFlyoutOpen) {

      this.updateLangFlyoutPosition();

    }

  }



  badgeCount(key?: string): number {
    if (key === 'adminChat') return this.unreadAdminChat;
    if (key === 'support') return this.unreadTickets || this.openTickets;
    if (key === 'notifications') return this.unreadNotifications;
    return 0;
  }

  badgeTone(key?: string): 'orange' | 'red' | 'default' {
    if (key === 'support') return 'orange';
    if (key === 'notifications') return 'red';
    return 'default';
  }



  toggleCollapse(): void {

    this.collapsed = !this.collapsed;

  }



  toggleAccountMenu(event: Event): void {

    event.stopPropagation();

    this.accountMenuOpen = !this.accountMenuOpen;

    if (!this.accountMenuOpen) {

      this.closeLangFlyout();

    }

  }



  onOpenProfile(event: Event): void {

    event.stopPropagation();

    this.accountMenuOpen = false;

    this.closeLangFlyout();

    this.openProfile.emit();

  }



  onOpenSettings(event: Event): void {

    event.stopPropagation();

    this.accountMenuOpen = false;

    this.closeLangFlyout();

    this.openSettings.emit();

  }



  onOpenHelp(event: Event): void {

    event.stopPropagation();

    this.accountMenuOpen = false;

    this.closeLangFlyout();

    this.openHelp.emit();

  }



  onSidebarAction(action: 'profile' | 'settings' | 'help'): void {

    if (action === 'profile') {

      this.openProfile.emit();

      return;

    }

    if (action === 'help') {

      this.openHelp.emit();

      return;

    }

    this.openSettings.emit();

  }



  onLogout(event: Event): void {

    event.stopPropagation();

    this.accountMenuOpen = false;

    this.closeLangFlyout();

    this.logout.emit();

  }



  toggleLangFlyout(event: Event): void {

    event.stopPropagation();

    this.langFlyoutOpen = !this.langFlyoutOpen;

    if (this.langFlyoutOpen) {

      setTimeout(() => this.updateLangFlyoutPosition(), 0);

    }

  }



  openLangFlyout(): void {

    this.cancelCloseLangFlyout();

    this.langFlyoutOpen = true;

    this.updateLangFlyoutPosition();

  }



  scheduleCloseLangFlyout(): void {

    this.langFlyoutCloseTimer = setTimeout(() => {

      this.langFlyoutOpen = false;

      this.langFlyoutCloseTimer = null;

    }, 180);

  }



  cancelCloseLangFlyout(): void {

    if (this.langFlyoutCloseTimer !== null) {

      clearTimeout(this.langFlyoutCloseTimer);

      this.langFlyoutCloseTimer = null;

    }

  }



  closeLangFlyout(): void {

    this.langFlyoutOpen = false;

  }



  selectLanguage(code: LangCode, event: Event): void {

    event.stopPropagation();

    if (this.i18n.langCode() === code) {

      return;

    }

    this.i18n.setLang(code);

    const current = this.prefs.read();

    this.prefs.write({ ...current, language: this.i18n.toDisplayName(code) });

    if (this.auth.token()) {

      this.auth.updateProfile({ preferred_language: code }).subscribe({ error: () => undefined });

      this.employee.updateSettings({ preferred_language: code }).subscribe({ error: () => undefined });

    }

    this.closeLangFlyout();

  }



  isActiveLang(code: LangCode): boolean {

    return this.i18n.langCode() === code;

  }



  private updateLangFlyoutPosition(): void {

    const el = this.langTrigger?.nativeElement;

    if (!el) return;

    const rect = el.getBoundingClientRect();

    const flyoutWidth = 228;

    const gap = 8;

    let left = rect.right + gap;

    const maxLeft = window.innerWidth - flyoutWidth - 12;

    if (left > maxLeft) {

      left = Math.max(12, rect.left - flyoutWidth - gap);

    }

    let top = rect.top;

    const maxTop = window.innerHeight - 160;

    if (top > maxTop) top = maxTop;

    this.langFlyoutTop = top;

    this.langFlyoutLeft = left;

  }



  private refreshBadges(): void {

    this.employee.getDashboard().subscribe({

      next: (ws) => {

        const s = ws.stats;

        this.unreadAdminChat = s.unread_admin_messages;

        this.commsState.setUnread(s.unread_admin_messages);

        this.openTickets = s.open_tickets;

        this.unreadTickets = s.unread_tickets ?? 0;

        this.helpdeskState.setUnread(this.unreadTickets);

        this.notifState.setUnread(s.unread_notifications ?? 0);

      },

    });

  }

}

