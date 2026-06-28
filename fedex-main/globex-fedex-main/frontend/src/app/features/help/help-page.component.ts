import { CommonModule } from '@angular/common';
import { Component, ElementRef, HostListener, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { I18nService } from '../../core/i18n/i18n.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import {
  HelpArticle,
  HelpArticleSummary,
  HelpCenterService,
  HelpContactOption,
  HelpMetrics,
  HelpResource,
} from '../../core/services/help-center.service';
import { FaqItem, SupportService } from '../../core/services/support.service';

type HelpCategory = 'all' | 'tracking' | 'documents' | 'account' | 'ai' | 'settings' | 'security';
type TicketCategory = 'tracking' | 'documents' | 'ai' | 'security' | 'account' | 'other';
type TicketPriority = 'low' | 'medium' | 'high';

@Component({
  selector: 'app-help-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, TranslatePipe],
  templateUrl: './help-page.component.html',
  styleUrl: './help-page.component.scss',
})
export class HelpPageComponent implements OnInit {
  @ViewChild('articlesSection') articlesSection?: ElementRef<HTMLElement>;
  @ViewChild('searchInput') searchInput?: ElementRef<HTMLInputElement>;

  items: FaqItem[] = [];
  loading = true;
  searchQuery = '';
  searchFocused = false;
  activeCategory: HelpCategory = 'all';

  resources: HelpResource[] = [];
  metrics: HelpMetrics | null = null;
  contactOptions: HelpContactOption[] = [];
  articles: HelpArticleSummary[] = [];
  loadingResources = true;
  loadingMetrics = true;
  loadingContactOptions = true;
  loadingArticles = true;
  articlesError = false;

  articleDrawerOpen = false;
  activeArticle: HelpArticle | null = null;
  loadingArticle = false;
  articleError = '';

  contactModalOpen = false;
  modalSubject = '';
  modalMessage = '';
  modalCategory: TicketCategory = 'tracking';
  modalPriority: TicketPriority = 'medium';
  submitting = false;
  uploadingAttachment = false;
  modalAttachmentUrl: string | null = null;
  modalAttachmentName = '';
  submitError = '';
  toastMessage = '';
  toastType: 'success' | 'error' | '' = '';

  readonly ticketCategories: { value: TicketCategory; labelKey: string }[] = [
    { value: 'tracking', labelKey: 'help.ticketCategory.tracking' },
    { value: 'documents', labelKey: 'help.ticketCategory.documents' },
    { value: 'ai', labelKey: 'help.ticketCategory.ai' },
    { value: 'security', labelKey: 'help.ticketCategory.security' },
    { value: 'account', labelKey: 'help.ticketCategory.account' },
    { value: 'other', labelKey: 'help.ticketCategory.other' },
  ];

  readonly priorityOptions: { value: TicketPriority; labelKey: string }[] = [
    { value: 'low', labelKey: 'help.priority.low' },
    { value: 'medium', labelKey: 'help.priority.medium' },
    { value: 'high', labelKey: 'help.priority.high' },
  ];

  private readonly iconBySlug: Record<string, string> = {
    'how-to-track-a-package': 'track',
    'how-to-find-eta': 'clock',
    'shipment-exceptions': 'alert',
    'delivery-issues': 'truck',
    'proof-of-delivery': 'doc',
    'export-excel': 'export',
    'download-reports': 'download',
    'archive-history': 'archive',
  };

  constructor(
    private readonly support: SupportService,
    private readonly helpCenter: HelpCenterService,
    private readonly i18n: I18nService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.loadFaq();
    this.loadHelpData();
    this.route.queryParamMap.subscribe((params) => {
      const articleSlug = params.get('article');
      if (articleSlug) {
        this.openArticle(articleSlug);
      }
      if (params.get('support') === '1' || params.get('support') === 'true') {
        this.openContactModal();
      }
    });
  }

  @HostListener('document:keydown', ['$event'])
  onGlobalKeydown(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.searchInput?.nativeElement.focus();
    }
    if (event.key === 'Escape') {
      if (this.articleDrawerOpen) {
        this.closeArticleDrawer();
      } else if (this.contactModalOpen) {
        this.closeContactModal();
      }
    }
  }

  get filteredArticles(): HelpArticleSummary[] {
    const q = this.searchQuery.trim().toLowerCase();
    let list = this.articles;
    if (this.activeCategory !== 'all') {
      list = list.filter((a) => a.category === this.activeCategory || this.categoryMatches(a.category, this.activeCategory));
    }
    if (!q) {
      return list;
    }
    return list.filter((a) => `${a.title} ${a.summary} ${a.category}`.toLowerCase().includes(q));
  }

  get searchSuggestions(): (FaqItem | HelpArticleSummary)[] {
    const q = this.searchQuery.trim().toLowerCase();
    if (!q) {
      return [...this.articles.slice(0, 4), ...this.items.slice(0, 3)];
    }
    const matchedArticles = this.articles
      .filter((a) => `${a.title} ${a.summary}`.toLowerCase().includes(q))
      .slice(0, 4);
    const matchedFaq = this.items
      .filter((item) => `${item.question} ${item.answer}`.toLowerCase().includes(q))
      .slice(0, 3);
    return [...matchedArticles, ...matchedFaq];
  }

  get showSearchDropdown(): boolean {
    return this.searchFocused && !this.loading && this.searchSuggestions.length > 0;
  }

  get displayMetrics(): HelpMetrics {
    return this.metrics ?? this.helpCenter.fallbackMetrics();
  }

  get displayResources(): HelpResource[] {
    return this.resources.length > 0 ? this.resources : this.helpCenter.fallbackResources();
  }

  get displayContactOptions(): HelpContactOption[] {
    return this.contactOptions.length > 0 ? this.contactOptions : this.helpCenter.fallbackContactOptions();
  }

  get relatedArticles(): HelpArticleSummary[] {
    if (!this.activeArticle?.relatedSlugs?.length) {
      return [];
    }
    return this.articles.filter((a) => this.activeArticle!.relatedSlugs.includes(a.slug));
  }

  formatTicketsSolved(value: number): string {
    return `${value.toLocaleString('en-US')}+`;
  }

  articleIconId(slug: string): string {
    return this.iconBySlug[slug] ?? 'doc';
  }

  categoryLabel(category: string): string {
    const map: Record<string, string> = {
      tracking: 'help.categoryTracking',
      documents: 'help.categoryDocuments',
      ai: 'help.categoryAi',
      security: 'help.categorySecurity',
      account: 'help.categoryAccount',
    };
    return this.i18n.t(map[category] ?? 'help.categoryAll');
  }

  loadFaq(): void {
    this.loading = true;
    this.support.getFaq(this.i18n.toBackendCode()).subscribe({
      next: (res) => {
        this.items = res.items;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  loadHelpData(): void {
    const lang = this.i18n.toBackendCode();
    this.loadingResources = true;
    this.loadingMetrics = true;
    this.loadingContactOptions = true;
    this.loadingArticles = true;
    this.articlesError = false;

    this.helpCenter.getResources(lang).subscribe({
      next: (res) => {
        this.resources = res;
        this.loadingResources = false;
      },
      error: () => {
        this.resources = this.helpCenter.fallbackResources();
        this.loadingResources = false;
      },
    });

    this.helpCenter.getMetrics().subscribe({
      next: (res) => {
        this.metrics = res;
        this.loadingMetrics = false;
      },
      error: () => {
        this.metrics = this.helpCenter.fallbackMetrics();
        this.loadingMetrics = false;
      },
    });

    this.helpCenter.getContactOptions().subscribe({
      next: (res) => {
        this.contactOptions = res;
        this.loadingContactOptions = false;
      },
      error: () => {
        this.contactOptions = this.helpCenter.fallbackContactOptions();
        this.loadingContactOptions = false;
      },
    });

    this.helpCenter.getArticles(lang).subscribe({
      next: (res) => {
        this.articles = res;
        this.loadingArticles = false;
      },
      error: () => {
        this.articles = [];
        this.articlesError = true;
        this.loadingArticles = false;
      },
    });
  }

  openArticle(slug: string): void {
    this.articleDrawerOpen = true;
    this.loadingArticle = true;
    this.articleError = '';
    this.activeArticle = null;
    document.body.style.overflow = 'hidden';

    this.helpCenter.getArticle(slug, this.i18n.toBackendCode()).subscribe({
      next: (article) => {
        if (!article) {
          this.loadingArticle = false;
          this.articleError = this.i18n.t('help.articleLoadError');
          return;
        }
        this.activeArticle = article;
        this.loadingArticle = false;
      },
      error: () => {
        this.loadingArticle = false;
        this.articleError = this.i18n.t('help.articleLoadError');
      },
    });
  }

  closeArticleDrawer(): void {
    this.articleDrawerOpen = false;
    this.activeArticle = null;
    this.articleError = '';
    document.body.style.overflow = '';
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { article: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  viewAllArticles(): void {
    this.activeCategory = 'all';
    this.searchQuery = '';
    this.scrollToArticles();
  }

  startAiChat(): void {
    void this.router.navigateByUrl('/chat');
  }

  openContactModal(): void {
    this.contactModalOpen = true;
    this.submitError = '';
  }

  closeContactModal(): void {
    this.contactModalOpen = false;
    this.clearModalAttachment();
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { support: null, new: null, ticket: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  openResource(resource: HelpResource): void {
    const cat = resource.category as HelpCategory;
    this.activeCategory = cat === 'security' ? 'account' : cat;
    this.scrollToArticles();
  }

  handleContactOption(option: HelpContactOption): void {
    if (option.action === 'chat') {
      this.startAiChat();
      return;
    }
    if (option.action === 'faq') {
      this.viewAllArticles();
      return;
    }
    this.openContactModal();
  }

  contactOptionStatusLabel(status: string): string {
    return status === 'available'
      ? this.i18n.t('help.contactStatusAvailable')
      : this.i18n.t('help.contactStatusUnavailable');
  }

  openSearchSuggestion(item: FaqItem | HelpArticleSummary): void {
    if ('slug' in item) {
      this.searchQuery = item.title;
      this.searchFocused = false;
      this.openArticle(item.slug);
      return;
    }
    this.searchQuery = item.question;
    this.searchFocused = false;
    this.openArticle(this.findArticleSlugForFaq(item) ?? 'how-to-track-a-package');
  }

  isArticleSuggestion(item: FaqItem | HelpArticleSummary): item is HelpArticleSummary {
    return 'slug' in item;
  }

  suggestionLabel(item: FaqItem | HelpArticleSummary): string {
    return this.isArticleSuggestion(item) ? item.title : item.question;
  }

  suggestionMeta(item: FaqItem | HelpArticleSummary): string {
    if (this.isArticleSuggestion(item)) {
      return `${this.categoryLabel(item.category)} · ${item.readTime}`;
    }
    return this.faqCategoryLabel(item);
  }

  onSearchBlur(): void {
    setTimeout(() => {
      this.searchFocused = false;
    }, 180);
  }

  faqCategoryLabel(item: FaqItem): string {
    const cat = this.inferCategory(item);
    const map: Record<HelpCategory, string> = {
      all: 'help.categoryAll',
      tracking: 'help.categoryTracking',
      documents: 'help.categoryDocuments',
      account: 'help.categoryAccount',
      ai: 'help.categoryAi',
      settings: 'help.categorySettings',
      security: 'help.categorySecurity',
    };
    return this.i18n.t(map[cat]);
  }

  resourceIconId(id: string): string {
    const map: Record<string, string> = {
      tracking: 'tracking',
      documents: 'documents',
      ai: 'ai',
      security: 'security',
    };
    return map[id] ?? 'tracking';
  }

  contactIconId(id: string): string {
    const map: Record<string, string> = {
      'ai-chat': 'ai',
      'live-support': 'contact',
      'email-support': 'email',
      'knowledge-base': 'faq',
    };
    return map[id] ?? 'contact';
  }

  formatUpdatedAt(dateStr: string): string {
    try {
      return new Intl.DateTimeFormat(this.i18n.toBackendCode(), {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      }).format(new Date(dateStr));
    } catch {
      return dateStr;
    }
  }

  onModalAttachmentSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    const err = this.support.validateAttachmentFile(file);
    if (err === 'type') {
      this.submitError = this.i18n.t('support.attachmentTypeError');
      return;
    }
    if (err === 'size') {
      this.submitError = this.i18n.t('support.attachmentSizeError');
      return;
    }
    this.uploadingAttachment = true;
    this.submitError = '';
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.uploadingAttachment = false;
        this.modalAttachmentUrl = res.url;
        this.modalAttachmentName = res.filename;
      },
      error: () => {
        this.uploadingAttachment = false;
        this.submitError = this.i18n.t('support.attachmentUploadError');
      },
    });
  }

  clearModalAttachment(): void {
    this.modalAttachmentUrl = null;
    this.modalAttachmentName = '';
  }

  submitContact(): void {
    const subject = this.modalSubject.trim();
    const message = this.modalMessage.trim();
    if (subject.length < 3 || message.length < 10) {
      this.submitError = this.i18n.t('help.formInvalid');
      return;
    }
    this.submitting = true;
    this.submitError = '';
    this.helpCenter
      .createTicket({
        subject,
        category: this.modalCategory,
        priority: this.modalPriority,
        message,
        attachmentUrl: this.modalAttachmentUrl,
      })
      .subscribe({
        next: () => {
          this.submitting = false;
          this.modalSubject = '';
          this.modalMessage = '';
          this.modalCategory = 'tracking';
          this.modalPriority = 'medium';
          this.clearModalAttachment();
          this.closeContactModal();
          this.showToast(this.i18n.t('help.toastSuccess'), 'success');
        },
        error: () => {
          this.submitting = false;
          this.submitError = this.i18n.t('help.formError');
          this.showToast(this.i18n.t('help.toastError'), 'error');
        },
      });
  }

  showToast(message: string, type: 'success' | 'error'): void {
    this.toastMessage = message;
    this.toastType = type;
    setTimeout(() => {
      if (this.toastMessage === message) {
        this.toastMessage = '';
        this.toastType = '';
      }
    }, 4200);
  }

  private scrollToArticles(): void {
    setTimeout(() => {
      this.articlesSection?.nativeElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 80);
  }

  private categoryMatches(articleCat: string, filter: HelpCategory): boolean {
    if (filter === 'account' && articleCat === 'security') {
      return true;
    }
    return articleCat === filter;
  }

  private findArticleSlugForFaq(item: FaqItem): string | null {
    const blob = `${item.question} ${item.answer}`.toLowerCase();
    if (/track|suivi|colis|parcel/.test(blob)) return 'how-to-track-a-package';
    if (/eta|delivery|livraison/.test(blob)) return 'how-to-find-eta';
    if (/exception|delay|retard/.test(blob)) return 'shipment-exceptions';
    if (/proof|pod|preuve/.test(blob)) return 'proof-of-delivery';
    if (/excel|export/.test(blob)) return 'export-excel';
    if (/report|pdf/.test(blob)) return 'download-reports';
    if (/archive|historique/.test(blob)) return 'archive-history';
    return null;
  }

  private inferCategory(item: FaqItem): HelpCategory {
    const blob = `${item.question} ${item.answer}`.toLowerCase();
    if (/colis|suivi|tracking|livraison|parcel|delivery|shipment|eta/.test(blob)) return 'tracking';
    if (/document|pdf|excel|export|preuve|proof|report/.test(blob)) return 'documents';
    if (/security|sécurité|qr|session|password/.test(blob)) return 'security';
    if (/compte|profil|connexion|account|login/.test(blob)) return 'account';
    if (/ai|assistant|claude|chat|préférence|preference/.test(blob)) return 'ai';
    if (/paramètre|settings|appearance|language/.test(blob)) return 'settings';
    return 'tracking';
  }
}
