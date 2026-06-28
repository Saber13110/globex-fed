import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { API_BASE_URL } from '../api.config';
import { FALLBACK_ARTICLE_SUMMARIES, fallbackArticle } from './help-articles.fallback';

export interface HelpResource {
  id: string;
  title: string;
  description: string;
  articlesCount: number;
  readTime: string;
  category: string;
}

export interface HelpMetrics {
  averageResponse: string;
  resolutionRate: string;
  ticketsSolved: number;
  satisfaction: string;
  supportOnline: boolean;
}

export interface HelpContactOption {
  id: string;
  title: string;
  description: string;
  status: string;
  cta: string;
  action: string;
}

export interface HelpArticleStep {
  title: string;
  body: string;
}

export interface HelpArticleFaqItem {
  question: string;
  answer: string;
}

export interface HelpArticleSection {
  type: string;
  heading?: string | null;
  body?: string | null;
  items?: string[] | null;
  steps?: HelpArticleStep[] | null;
  faq?: HelpArticleFaqItem[] | null;
}

export interface HelpArticleSummary {
  id: string;
  slug: string;
  title: string;
  category: string;
  summary: string;
  readTime: string;
  updatedAt: string;
}

export interface HelpArticle extends HelpArticleSummary {
  sections: HelpArticleSection[];
  relatedSlugs: string[];
}

export interface CreateTicketPayload {
  subject: string;
  category: string;
  priority: string;
  message: string;
  attachmentUrl?: string | null;
}

export interface CreateTicketResponse {
  success: boolean;
  ticketId: string;
  id: number;
  status: string;
  createdAt: string;
}

export interface SupportTicketSummary {
  id: number;
  ticket_number?: string;
  subject: string;
  message: string;
  category: string;
  priority: string;
  status: string;
  attachment_url?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface SupportTicketListResponse {
  items: SupportTicketSummary[];
}

const FALLBACK_RESOURCES: HelpResource[] = [
  {
    id: 'tracking',
    title: 'Tracking issues',
    description: 'Track parcels, ETA, exceptions and delivery problems.',
    articlesCount: 8,
    readTime: '2 min read',
    category: 'tracking',
  },
  {
    id: 'documents',
    title: 'Documents & POD',
    description: 'Manage proofs of delivery, exports and archived reports.',
    articlesCount: 6,
    readTime: '3 min read',
    category: 'documents',
  },
  {
    id: 'ai',
    title: 'AI Assistant',
    description: 'Customize answers, preferences and smart suggestions.',
    articlesCount: 5,
    readTime: '2 min read',
    category: 'ai',
  },
  {
    id: 'security',
    title: 'Security',
    description: 'Manage sessions, QR login and account protection.',
    articlesCount: 4,
    readTime: '3 min read',
    category: 'security',
  },
];

const FALLBACK_METRICS: HelpMetrics = {
  averageResponse: '< 5 min',
  resolutionRate: '98.7%',
  ticketsSolved: 12000,
  satisfaction: '4.9/5',
  supportOnline: true,
};

const FALLBACK_CONTACT_OPTIONS: HelpContactOption[] = [
  {
    id: 'ai-chat',
    title: 'AI Chat',
    description: 'Instant AI assistance for tracking and documents.',
    status: 'available',
    cta: 'Start',
    action: 'chat',
  },
  {
    id: 'live-support',
    title: 'Live Support',
    description: 'Connect with our FedEx AI support team.',
    status: 'available',
    cta: 'Contact',
    action: 'contact',
  },
  {
    id: 'email-support',
    title: 'Email Support',
    description: 'Send a detailed request and receive a written response.',
    status: 'available',
    cta: 'Send',
    action: 'contact',
  },
  {
    id: 'knowledge-base',
    title: 'Knowledge Base',
    description: 'Browse articles, guides and frequently asked questions.',
    status: 'available',
    cta: 'Browse',
    action: 'faq',
  },
];

@Injectable({ providedIn: 'root' })
export class HelpCenterService {
  constructor(private readonly http: HttpClient) {}

  getResources(lang?: string): Observable<HelpResource[]> {
    const q = lang ? `?lang=${encodeURIComponent(lang)}` : '';
    return this.http.get<HelpResource[]>(`${API_BASE_URL}/api/help/resources${q}`);
  }

  getMetrics(): Observable<HelpMetrics> {
    return this.http.get<HelpMetrics>(`${API_BASE_URL}/api/help/metrics`);
  }

  getContactOptions(): Observable<HelpContactOption[]> {
    return this.http.get<HelpContactOption[]>(`${API_BASE_URL}/api/help/contact-options`);
  }

  getArticles(lang?: string): Observable<HelpArticleSummary[]> {
    const q = lang ? `?lang=${encodeURIComponent(lang)}` : '';
    return this.http.get<HelpArticleSummary[]>(`${API_BASE_URL}/api/help/articles${q}`).pipe(
      catchError(() => of(FALLBACK_ARTICLE_SUMMARIES.map((a) => ({ ...a })))),
    );
  }

  getArticle(slug: string, lang?: string): Observable<HelpArticle> {
    const q = lang ? `?lang=${encodeURIComponent(lang)}` : '';
    return this.http.get<HelpArticle>(`${API_BASE_URL}/api/help/articles/${encodeURIComponent(slug)}${q}`).pipe(
      catchError(() => {
        const fb = fallbackArticle(slug);
        return fb ? of(fb) : of(null as unknown as HelpArticle);
      }),
    );
  }

  createTicket(payload: CreateTicketPayload): Observable<CreateTicketResponse> {
    return this.http.post<CreateTicketResponse>(`${API_BASE_URL}/api/support/tickets`, payload);
  }

  getMyTickets(): Observable<SupportTicketListResponse> {
    return this.http.get<SupportTicketListResponse>(`${API_BASE_URL}/api/support/tickets/me`);
  }

  getTicket(id: number): Observable<unknown> {
    return this.http.get(`${API_BASE_URL}/api/support/tickets/${id}`);
  }

  fallbackResources(): HelpResource[] {
    return FALLBACK_RESOURCES.map((r) => ({ ...r }));
  }

  fallbackMetrics(): HelpMetrics {
    return { ...FALLBACK_METRICS };
  }

  fallbackContactOptions(): HelpContactOption[] {
    return FALLBACK_CONTACT_OPTIONS.map((o) => ({ ...o }));
  }

  fallbackArticles(): HelpArticleSummary[] {
    return FALLBACK_ARTICLE_SUMMARIES.map((a) => ({ ...a }));
  }
}
