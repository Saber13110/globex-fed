import { UiMessage } from '../message-list/message-list.component';

export type ConversationKind = 'tracking' | 'export' | 'proof' | 'issue' | 'general';

export function detectConversationKind(title: string, messages: UiMessage[] = []): ConversationKind {
  const t = title.toLowerCase();
  if (/preuve|proof|pdf|livraison|delivery|pod/.test(t)) return 'proof';
  if (/export|excel|rapport|report|march|historique|history|performance/.test(t)) return 'export';
  if (/problème|problem|issue|retard|delay|support|incident/.test(t)) return 'issue';
  if (/suivi|track|parcel|colis|shipment|tracking/.test(t)) return 'tracking';
  if (messages.some((m) => m.shipment)) return 'tracking';
  return 'general';
}

export function conversationEmoji(kind: ConversationKind): string {
  const map: Record<ConversationKind, string> = {
    tracking: '📦',
    export: '📊',
    proof: '📄',
    issue: '⚠️',
    general: '💬',
  };
  return map[kind];
}

export function conversationCategoryKey(kind: ConversationKind): string {
  const map: Record<ConversationKind, string> = {
    tracking: 'conversation.category.tracking',
    export: 'conversation.category.export',
    proof: 'conversation.category.proof',
    issue: 'conversation.category.issue',
    general: 'conversation.category.general',
  };
  return map[kind];
}

export function formatRelativeActivity(
  iso: string,
  t: (key: string, params?: Record<string, string>) => string,
): string {
  if (!iso?.trim()) {
    return '';
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) {
    return t('conversation.time.justNow');
  }
  if (diffMin < 60) {
    return t('conversation.time.minutesAgo', { count: String(diffMin) });
  }
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) {
    return t('conversation.time.hoursAgo', { count: String(diffHours) });
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) {
    return t('conversation.time.yesterday');
  }
  if (diffDays < 7) {
    return t('conversation.time.daysAgo', { count: String(diffDays) });
  }
  return date.toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
}

export function userInitial(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) {
    return '?';
  }
  return trimmed.charAt(0).toUpperCase();
}
