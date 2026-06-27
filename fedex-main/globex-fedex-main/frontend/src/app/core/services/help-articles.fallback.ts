import { HelpArticle, HelpArticleSummary } from './help-center.service';

export const FALLBACK_ARTICLE_SUMMARIES: HelpArticleSummary[] = [
  { id: '1', slug: 'how-to-track-a-package', title: 'How to track a package', category: 'tracking', summary: 'Enter your tracking number, view real-time status, ETA and notifications.', readTime: '4 min read', updatedAt: '2025-06-01' },
  { id: '2', slug: 'how-to-find-eta', title: 'How to find ETA', category: 'tracking', summary: 'Locate estimated delivery dates, time windows and delivery commitments.', readTime: '3 min read', updatedAt: '2025-05-28' },
  { id: '3', slug: 'shipment-exceptions', title: 'Shipment exceptions', category: 'tracking', summary: 'Understand delay codes, holds, customs issues and how to resolve them.', readTime: '5 min read', updatedAt: '2025-05-25' },
  { id: '4', slug: 'delivery-issues', title: 'Delivery issues', category: 'tracking', summary: 'Resolve missed deliveries, wrong addresses, damaged packages and proof requests.', readTime: '4 min read', updatedAt: '2025-05-22' },
  { id: '5', slug: 'proof-of-delivery', title: 'Proof of delivery', category: 'documents', summary: 'Access, download and share POD documents and delivery signatures.', readTime: '3 min read', updatedAt: '2025-05-20' },
  { id: '6', slug: 'export-excel', title: 'Export Excel', category: 'documents', summary: 'Export tracking history and shipment data to Excel spreadsheets.', readTime: '3 min read', updatedAt: '2025-05-18' },
  { id: '7', slug: 'download-reports', title: 'Download reports', category: 'documents', summary: 'Generate and download PDF summaries, analytics reports and audit logs.', readTime: '4 min read', updatedAt: '2025-05-15' },
  { id: '8', slug: 'archive-history', title: 'Archive history', category: 'documents', summary: 'Archive, restore and manage long-term tracking history records.', readTime: '3 min read', updatedAt: '2025-05-12' },
];

const FALLBACK_DETAILS: Record<string, HelpArticle> = {
  'how-to-track-a-package': {
    ...FALLBACK_ARTICLE_SUMMARIES[0],
    relatedSlugs: ['how-to-find-eta', 'shipment-exceptions'],
    sections: [
      { type: 'paragraph', body: 'FedEx AI Tracking lets you monitor any shipment in real time from the chat or Tracking History page.' },
      { type: 'steps', heading: 'Step-by-step', steps: [
        { title: 'Open the AI chat or History page', body: 'From the sidebar, click Chat or History.' },
        { title: 'Enter your tracking number', body: 'Type a valid FedEx tracking number (12 or 14 digits).' },
        { title: 'Review the shipment timeline', body: 'See status, last scan location, ETA and exceptions.' },
        { title: 'Enable notifications', body: 'Settings → Notifications for email or in-app alerts.' },
      ]},
      { type: 'tips', heading: 'Pro tips', items: ['Save frequent numbers as favorites.', 'Ask the AI for a natural-language summary.', 'Check Shipment exceptions if status is stale.'] },
      { type: 'faq', heading: 'Common errors', faq: [
        { question: 'Invalid tracking number', answer: 'Verify all digits — 12 or 14 characters, no special characters.' },
        { question: 'No information available', answer: 'Wait 2–4 hours after pickup, then retry.' },
      ]},
    ],
  },
};

export function fallbackArticle(slug: string): HelpArticle | null {
  return FALLBACK_DETAILS[slug] ?? null;
}
