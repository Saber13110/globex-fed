export type ThinkingAnimation = 'bounce' | 'pulse' | 'wave';

export const THINKING_ANIMATION_OPTIONS: { id: ThinkingAnimation; labelKey: string }[] = [
  { id: 'bounce', labelKey: 'settings.thinkingAnim.bounce' },
  { id: 'pulse', labelKey: 'settings.thinkingAnim.pulse' },
  { id: 'wave', labelKey: 'settings.thinkingAnim.wave' },
];

export function normalizeThinkingAnimation(value: unknown): ThinkingAnimation {
  if (value === 'bounce' || value === 'pulse' || value === 'wave') {
    return value;
  }
  return 'bounce';
}
