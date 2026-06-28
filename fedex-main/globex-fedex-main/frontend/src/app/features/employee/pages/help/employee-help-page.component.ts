import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { EMPTY, Subject, debounceTime, distinctUntilChanged, switchMap, takeUntil } from 'rxjs';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { EmployeePortalService, EmployeeSearchHit } from '../../../../core/services/employee-portal.service';

interface KnowledgeCategory {
  id: string;
  icon: string;
  titleKey: string;
  descKey: string;
  route: string;
  keywords: string[];
}

interface KnowledgeProcedure {
  id: string;
  icon: string;
  titleKey: string;
  descKey: string;
  route: string;
  keywords: string[];
}

interface KnowledgeFaq {
  id: string;
  questionKey: string;
  answerKey: string;
  keywords: string[];
}

interface LocalSearchHit {
  id: string;
  kind: 'procedure' | 'category' | 'faq';
  titleKey: string;
  subtitleKey: string;
  route?: string;
  faqId?: string;
}

@Component({
  selector: 'app-employee-help-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './employee-help-page.component.html',
  styleUrl: './employee-help-page.component.scss',
})
export class EmployeeHelpPageComponent implements OnInit, OnDestroy {
  q = '';
  searching = false;
  showSearchResults = false;
  apiHits: EmployeeSearchHit[] = [];
  localHits: LocalSearchHit[] = [];
  expandedFaq: string | null = null;

  readonly categories: KnowledgeCategory[] = [
    {
      id: 'support',
      icon: 'ticket',
      titleKey: 'employee.knowledge.cat.support.title',
      descKey: 'employee.knowledge.cat.support.desc',
      route: '/employee/support',
      keywords: ['support', 'ticket', 'helpdesk', 'reply', 'escalate', 'client'],
    },
    {
      id: 'tracking',
      icon: 'package',
      titleKey: 'employee.knowledge.cat.tracking.title',
      descKey: 'employee.knowledge.cat.tracking.desc',
      route: '/employee/tracking',
      keywords: ['tracking', 'shipment', 'fedex', 'exception', 'delivery', 'suivi', 'colis'],
    },
    {
      id: 'documents',
      icon: 'file',
      titleKey: 'employee.knowledge.cat.documents.title',
      descKey: 'employee.knowledge.cat.documents.desc',
      route: '/employee/clients',
      keywords: ['document', 'pod', 'proof', 'pdf', 'export', 'report'],
    },
    {
      id: 'clients',
      icon: 'users',
      titleKey: 'employee.knowledge.cat.clients.title',
      descKey: 'employee.knowledge.cat.clients.desc',
      route: '/employee/clients',
      keywords: ['client', 'customer', 'profile', '360', 'account'],
    },
    {
      id: 'tools',
      icon: 'bot',
      titleKey: 'employee.knowledge.cat.tools.title',
      descKey: 'employee.knowledge.cat.tools.desc',
      route: '/employee/ai-assistant',
      keywords: ['ai', 'assistant', 'tool', 'admin', 'notification', 'chat'],
    },
  ];

  readonly procedures: KnowledgeProcedure[] = [
    {
      id: 'reply-ticket',
      icon: 'ticket',
      titleKey: 'employee.knowledge.proc.replyTicket.title',
      descKey: 'employee.knowledge.proc.replyTicket.desc',
      route: '/employee/support',
      keywords: ['reply', 'ticket', 'respond', 'support', 'message'],
    },
    {
      id: 'tracking-exception',
      icon: 'alert',
      titleKey: 'employee.knowledge.proc.trackingException.title',
      descKey: 'employee.knowledge.proc.trackingException.desc',
      route: '/employee/tracking',
      keywords: ['exception', 'delay', 'tracking', 'shipment', 'problem'],
    },
    {
      id: 'download-pod',
      icon: 'file',
      titleKey: 'employee.knowledge.proc.downloadPod.title',
      descKey: 'employee.knowledge.proc.downloadPod.desc',
      route: '/employee/tracking',
      keywords: ['pod', 'proof', 'delivery', 'download', 'document'],
    },
    {
      id: 'client-search',
      icon: 'users',
      titleKey: 'employee.knowledge.proc.clientSearch.title',
      descKey: 'employee.knowledge.proc.clientSearch.desc',
      route: '/employee/clients',
      keywords: ['client', 'search', 'customer', 'find', 'profile'],
    },
    {
      id: 'escalation',
      icon: 'alert',
      titleKey: 'employee.knowledge.proc.escalation.title',
      descKey: 'employee.knowledge.proc.escalation.desc',
      route: '/employee/support',
      keywords: ['escalate', 'admin', 'urgent', 'priority', 'ticket'],
    },
    {
      id: 'create-report',
      icon: 'file',
      titleKey: 'employee.knowledge.proc.createReport.title',
      descKey: 'employee.knowledge.proc.createReport.desc',
      route: '/employee/clients',
      keywords: ['report', 'generate', 'export', 'document'],
    },
    {
      id: 'export-history',
      icon: 'package',
      titleKey: 'employee.knowledge.proc.exportHistory.title',
      descKey: 'employee.knowledge.proc.exportHistory.desc',
      route: '/employee/tracking-history',
      keywords: ['history', 'export', 'tracking', 'archive'],
    },
    {
      id: 'document-retrieval',
      icon: 'file',
      titleKey: 'employee.knowledge.proc.documentRetrieval.title',
      descKey: 'employee.knowledge.proc.documentRetrieval.desc',
      route: '/employee/clients',
      keywords: ['document', 'retrieve', 'download', 'file', 'client'],
    },
    {
      id: 'chat-admin',
      icon: 'message',
      titleKey: 'employee.knowledge.proc.chatAdmin.title',
      descKey: 'employee.knowledge.proc.chatAdmin.desc',
      route: '/employee/admin-chat',
      keywords: ['admin', 'chat', 'contact', 'validation', 'message'],
    },
    {
      id: 'notifications',
      icon: 'bell',
      titleKey: 'employee.knowledge.proc.notifications.title',
      descKey: 'employee.knowledge.proc.notifications.desc',
      route: '/employee/notifications',
      keywords: ['notification', 'alert', 'unread', 'bell', 'inbox'],
    },
  ];

  readonly faqItems: KnowledgeFaq[] = [
    {
      id: 'reply',
      questionKey: 'employee.knowledge.faq.reply.q',
      answerKey: 'employee.knowledge.faq.reply.a',
      keywords: ['reply', 'ticket', 'respond', 'message', 'client'],
    },
    {
      id: 'escalate',
      questionKey: 'employee.knowledge.faq.escalate.q',
      answerKey: 'employee.knowledge.faq.escalate.a',
      keywords: ['escalate', 'admin', 'urgent', 'priority'],
    },
    {
      id: 'pod',
      questionKey: 'employee.knowledge.faq.pod.q',
      answerKey: 'employee.knowledge.faq.pod.a',
      keywords: ['pod', 'proof', 'delivery', 'download'],
    },
    {
      id: 'exception',
      questionKey: 'employee.knowledge.faq.exception.q',
      answerKey: 'employee.knowledge.faq.exception.a',
      keywords: ['exception', 'delay', 'shipment', 'tracking'],
    },
    {
      id: 'admin',
      questionKey: 'employee.knowledge.faq.admin.q',
      answerKey: 'employee.knowledge.faq.admin.a',
      keywords: ['admin', 'contact', 'chat', 'validation'],
    },
    {
      id: 'client',
      questionKey: 'employee.knowledge.faq.client.q',
      answerKey: 'employee.knowledge.faq.client.a',
      keywords: ['client', 'search', 'customer', 'find'],
    },
  ];

  private readonly destroy$ = new Subject<void>();
  private readonly search$ = new Subject<string>();

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.search$
      .pipe(
        debounceTime(280),
        distinctUntilChanged(),
        switchMap((term) => {
          const trimmed = term.trim();
          this.localHits = this.searchLocal(trimmed);
          if (trimmed.length < 2) {
            this.apiHits = [];
            this.showSearchResults = trimmed.length > 0 && this.localHits.length > 0;
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
          this.apiHits = res.items;
          this.showSearchResults = this.q.trim().length >= 1;
          this.searching = false;
        },
        error: () => {
          this.searching = false;
          this.showSearchResults = this.q.trim().length >= 1;
        },
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onSearchInput(): void {
    this.search$.next(this.q);
    if (!this.q.trim()) {
      this.apiHits = [];
      this.localHits = [];
      this.showSearchResults = false;
    }
  }

  clearSearch(): void {
    this.q = '';
    this.apiHits = [];
    this.localHits = [];
    this.showSearchResults = false;
  }

  scrollTo(id: string): void {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  toggleFaq(id: string): void {
    this.expandedFaq = this.expandedFaq === id ? null : id;
  }

  openApiHit(hit: EmployeeSearchHit): void {
    this.clearSearch();
    void this.router.navigateByUrl(hit.link);
  }

  openLocalHit(hit: LocalSearchHit): void {
    this.clearSearch();
    if (hit.faqId) {
      this.expandedFaq = hit.faqId;
      this.scrollTo('knowledge-faq');
      return;
    }
    if (hit.route) {
      void this.router.navigateByUrl(hit.route);
    }
  }

  searchKindLabel(kind: string): string {
    const map: Record<string, string> = {
      client: 'employee.knowledge.hit.client',
      tracking: 'employee.knowledge.hit.tracking',
      ticket: 'employee.knowledge.hit.ticket',
      notification: 'employee.knowledge.hit.notification',
      procedure: 'employee.knowledge.hit.procedure',
      category: 'employee.knowledge.hit.category',
      faq: 'employee.knowledge.hit.faq',
    };
    return map[kind] || kind;
  }

  hasSearchResults(): boolean {
    return this.localHits.length > 0 || this.apiHits.length > 0;
  }

  private searchLocal(query: string): LocalSearchHit[] {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];

    const hits: LocalSearchHit[] = [];
    const matches = (keywords: string[]) => keywords.some((k) => k.includes(needle) || needle.includes(k));

    for (const p of this.procedures) {
      if (matches(p.keywords)) {
        hits.push({
          id: p.id,
          kind: 'procedure',
          titleKey: p.titleKey,
          subtitleKey: p.descKey,
          route: p.route,
        });
      }
    }
    for (const c of this.categories) {
      if (matches(c.keywords)) {
        hits.push({
          id: c.id,
          kind: 'category',
          titleKey: c.titleKey,
          subtitleKey: c.descKey,
          route: c.route,
        });
      }
    }
    for (const f of this.faqItems) {
      if (matches(f.keywords)) {
        hits.push({
          id: f.id,
          kind: 'faq',
          titleKey: f.questionKey,
          subtitleKey: f.answerKey,
          faqId: f.id,
        });
      }
    }
    return hits.slice(0, 8);
  }
}
