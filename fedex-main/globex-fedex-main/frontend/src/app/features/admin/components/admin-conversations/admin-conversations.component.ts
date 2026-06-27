import { CommonModule } from '@angular/common';
import { Component, EventEmitter, HostListener, Input, OnInit, Output, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import {
  AdminConversationDetail,
  AdminConversationListItem,
  AdminConversationsPage,
  AdminConversationsService,
} from '../../../../core/services/admin-conversations.service';
import { AdminService } from '../../../../core/services/admin.service';
import { AdminMessagingHubComponent } from '../admin-messaging-hub/admin-messaging-hub.component';
import { AdminUserSuspendActionsComponent } from '../admin-user-suspend-actions/admin-user-suspend-actions.component';

type ConvTab = 'all' | 'unread' | 'tracking' | 'reports' | 'analytics';

export type ConvNavigateEvent =
  | { target: 'users'; userId: number }
  | { target: 'incidents' };

const LIST_PREVIEW_LIMIT = 5;

@Component({
  selector: 'app-admin-conversations',
  standalone: true,
  imports: [CommonModule, FormsModule, AdminMessagingHubComponent, AdminUserSuspendActionsComponent],
  templateUrl: './admin-conversations.component.html',
  styleUrl: './admin-conversations.component.scss',
})
export class AdminConversationsComponent implements OnInit {
  @Input() initialConversationId: number | null = null;
  @Output() openUserTicket = new EventEmitter<number>();
  @Output() navigate = new EventEmitter<ConvNavigateEvent>();

  readonly messagingOpen = signal(false);
  readonly headMenuOpen = signal(false);
  readonly actionBusy = signal(false);

  readonly tabs: { id: ConvTab; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'unread', label: 'Unread' },
    { id: 'tracking', label: 'Tracking' },
    { id: 'reports', label: 'Reports' },
    { id: 'analytics', label: 'Analytics' },
  ];

  readonly activeTab = signal<ConvTab>('all');
  readonly listSearch = signal('');
  readonly loading = signal(true);
  readonly detailLoading = signal(false);
  readonly kpis = signal<AdminConversationsPage['kpis']>([]);
  readonly conversations = signal<AdminConversationListItem[]>([]);
  readonly selectedId = signal<number | null>(null);
  readonly detail = signal<AdminConversationDetail | null>(null);
  readonly composerText = signal('');
  readonly typing = signal(false);
  readonly showAllList = signal(false);

  readonly visibleConversations = computed(() => {
    const all = this.conversations();
    return this.showAllList() ? all : all.slice(0, LIST_PREVIEW_LIMIT);
  });

  constructor(
    private readonly convService: AdminConversationsService,
    private readonly admin: AdminService,
  ) {}

  ngOnInit(): void {
    this.loadPage();
  }

  toggleMessaging(): void {
    const next = !this.messagingOpen();
    this.messagingOpen.set(next);
    if (next) {
      setTimeout(() => {
        document.getElementById('admin-conv-messaging')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 80);
    }
  }

  onOpenUserTicket(ticketId: number): void {
    this.openUserTicket.emit(ticketId);
  }

  loadPage(): void {
    this.loading.set(true);
    this.showAllList.set(false);
    this.convService.list(this.activeTab(), this.listSearch()).subscribe({
      next: (page) => {
        this.kpis.set(page.kpis);
        this.conversations.set(page.conversations);
        this.loading.set(false);
        const preferredId = this.initialConversationId;
        const sel = preferredId ?? this.selectedId();
        const first = page.conversations[0];
        if (preferredId != null && page.conversations.some((c) => c.id === preferredId)) {
          this.selectConversation(preferredId);
        } else if (!sel && first) {
          this.selectConversation(first.id);
        } else if (sel && !page.conversations.some((c) => c.id === sel) && first) {
          this.selectConversation(first.id);
        } else if (sel) {
          this.loadDetail(sel);
        }
      },
      error: () => {
        const demo = this.demoPage();
        this.kpis.set(demo.kpis);
        this.conversations.set(demo.conversations);
        this.loading.set(false);
        if (demo.conversations[0]) {
          this.selectConversation(demo.conversations[0].id, true);
        }
      },
    });
  }

  setTab(tab: ConvTab): void {
    this.activeTab.set(tab);
    this.loadPage();
  }

  onListSearch(): void {
    this.loadPage();
  }

  viewAllConversations(): void {
    this.showAllList.set(true);
  }

  collapseList(): void {
    this.showAllList.set(false);
    const el = document.querySelector('.conv-list__items');
    el?.scrollTo({ top: 0, behavior: 'smooth' });
  }

  selectConversation(id: number, demo = false): void {
    this.selectedId.set(id);
    if (demo) {
      this.detail.set(this.demoDetail(id));
      return;
    }
    this.loadDetail(id);
  }

  private loadDetail(id: number): void {
    this.detailLoading.set(true);
    this.convService.detail(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.detailLoading.set(false);
        this.typing.set(d.is_unread);
      },
      error: () => {
        this.detail.set(this.demoDetail(id));
        this.detailLoading.set(false);
        this.typing.set(true);
      },
    });
  }

  statusBadgeClass(item: AdminConversationListItem): string {
    if (item.status_key === 'unread' || item.is_unread) return 'conv-badge--unread';
    if (item.category === 'Tracking') return 'conv-badge--tracking';
    if (item.category === 'Reports') return 'conv-badge--report';
    if (item.category === 'Analytics') return 'conv-badge--analytics';
    return 'conv-badge--default';
  }

  priorityDotClass(priority: string): string {
    const p = priority.toLowerCase();
    if (p === 'high') return 'conv-priority--high';
    if (p === 'low') return 'conv-priority--low';
    return 'conv-priority--medium';
  }

  kpiIcon(icon: string): string {
    const map: Record<string, string> = {
      chat: 'M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z',
      mail: 'M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z',
      spark: 'M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z',
      truck: 'M18 18.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zm-10 0a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zM20 8h-3V6H6v12h1.5a3 3 0 0 1 5.7 0H15a3 3 0 0 1 5.7 0H21V8h-1z',
    };
    return map[icon] ?? map['chat'];
  }

  sendMessage(): void {
    const text = this.composerText().trim();
    if (!text) return;
    this.composerText.set('');
    this.typing.set(false);
  }

  onUserSuspended(): void {
    const id = this.selectedId();
    if (id != null) {
      this.loadDetail(id);
    }
    this.loadPage();
    this.headMenuOpen.set(false);
  }

  toggleHeadMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.headMenuOpen.update((v) => !v);
  }

  closeHeadMenu(): void {
    this.headMenuOpen.set(false);
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.headMenuOpen.set(false);
  }

  openUserAccount(d: AdminConversationDetail): void {
    if (!d.user_id) return;
    this.closeHeadMenu();
    this.navigate.emit({ target: 'users', userId: d.user_id });
  }

  openSecurityIds(): void {
    this.closeHeadMenu();
    this.navigate.emit({ target: 'incidents' });
  }

  copyUserEmail(email: string): void {
    if (!email) return;
    navigator.clipboard.writeText(email).then(
      () => this.closeHeadMenu(),
      () => alert('Impossible de copier l\'e-mail.'),
    );
  }

  suspendFromMenu(d: AdminConversationDetail): void {
    if (!d.user_id || this.actionBusy()) return;
    const label = d.user_name || d.user_email || 'cet utilisateur';
    if (!confirm(`Suspendre le compte de ${label} ?\n\nL'utilisateur ne pourra plus utiliser le chat ni l'agent IA.`)) return;
    this.actionBusy.set(true);
    this.admin.suspendUser(d.user_id, `Suspension depuis conversation chat — ${d.title}`).subscribe({
      next: () => {
        this.actionBusy.set(false);
        this.onUserSuspended();
      },
      error: (err: HttpErrorResponse) => {
        this.actionBusy.set(false);
        alert(typeof err.error?.detail === 'string' ? err.error.detail : 'Suspension impossible.');
      },
    });
  }

  reactivateFromMenu(d: AdminConversationDetail): void {
    if (!d.user_id || this.actionBusy()) return;
    const label = d.user_name || d.user_email || 'cet utilisateur';
    if (!confirm(`Réactiver le compte de ${label} ?`)) return;
    this.actionBusy.set(true);
    this.admin.reactivateUser(d.user_id).subscribe({
      next: () => {
        this.actionBusy.set(false);
        this.onUserSuspended();
      },
      error: (err: HttpErrorResponse) => {
        this.actionBusy.set(false);
        alert(typeof err.error?.detail === 'string' ? err.error.detail : 'Réactivation impossible.');
      },
    });
  }

  private demoPage(): AdminConversationsPage {
    return {
      kpis: [
        { label: 'Total Conversations', value: 248, trend_percent: 12.5, trend_up: true, icon: 'chat' },
        { label: 'Unread', value: 12, trend_percent: 5.2, trend_up: true, icon: 'mail' },
        { label: 'AI Reports', value: 83, trend_percent: 8.1, trend_up: true, icon: 'spark' },
        { label: 'Tracking Requests', value: 125, trend_percent: 15.3, trend_up: true, icon: 'truck' },
      ],
      conversations: [
        {
          id: 1,
          session_id: 1,
          title: 'Assistance suivi FedEx',
          preview: 'Bonjour Ana, comment puis-je vous aider aujourd\'hui concernant le suivi de vos colis FedEx ?',
          user_id: 1,
          user_name: 'Jessy',
          user_email: 'jessy@example.com',
          user_status: 'active',
          user_initial: 'J',
          category: 'Tracking',
          status: 'Unread',
          status_key: 'unread',
          priority: 'Medium',
          is_unread: true,
          updated_label: '2 min ago',
          created_at: new Date().toISOString(),
        },
        {
          id: 2,
          session_id: 2,
          title: 'Suivi colis FedEx',
          preview: 'Votre colis est en transit vers Casablanca.',
          user_id: 2,
          user_name: 'Ana',
          user_email: 'ana@example.com',
          user_status: 'active',
          user_initial: 'A',
          category: 'Tracking',
          status: 'Active',
          status_key: 'active',
          priority: 'Medium',
          is_unread: false,
          updated_label: '1h ago',
          created_at: new Date().toISOString(),
        },
        {
          id: 3,
          session_id: 3,
          title: 'Q4 Performance Report',
          preview: 'Voici le résumé des performances opérationnelles du trimestre.',
          user_id: 3,
          user_name: 'Karim',
          user_email: 'karim@example.com',
          user_status: 'active',
          user_initial: 'K',
          category: 'Reports',
          status: 'Active',
          status_key: 'active',
          priority: 'Low',
          is_unread: false,
          updated_label: 'Yesterday',
          created_at: new Date().toISOString(),
        },
      ],
    };
  }

  private demoDetail(id: number): AdminConversationDetail {
    return {
      id,
      session_id: id,
      title: 'Assistance suivi FedEx',
      user_id: 1,
      user_name: 'Jessy',
      user_email: 'jessy@example.com',
      user_status: 'active',
      user_initial: 'J',
      category: 'Tracking',
      status: 'Unread',
      status_key: 'unread',
      priority: 'Medium',
      channel: 'AI Assistant',
      created_at: new Date().toISOString(),
      created_label: '01/06/26 18:31',
      updated_label: '2 min ago',
      is_unread: true,
      tags: ['tracking', 'support', 'shipment', 'priority:medium'],
      messages: [
        {
          id: 1,
          sender: 'bot',
          message_text:
            'Bonjour Ana, comment puis-je vous aider aujourd\'hui concernant le suivi de vos colis FedEx ?',
          created_at: new Date().toISOString(),
          time_label: '18:31',
        },
        {
          id: 2,
          sender: 'user',
          message_text: 'Bonjour, je souhaite connaître le statut de mon colis numéro 123456789.',
          created_at: new Date().toISOString(),
          time_label: '18:32',
        },
        {
          id: 3,
          sender: 'bot',
          message_text: 'Je vérifie immédiatement le statut de votre colis 123456789. Veuillez patienter un instant.',
          created_at: new Date().toISOString(),
          time_label: '18:32',
        },
      ],
      analytics: {
        response_time: '2.4s',
        response_time_trend: -12,
        resolution_time: '15m 32s',
        resolution_time_trend: -8,
        satisfaction: '98%',
        satisfaction_trend: 5,
        messages: 6,
        interactions: 3,
      },
    };
  }
}
