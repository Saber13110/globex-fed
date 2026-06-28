import { LangCode, TranslationMap } from '../i18n.types';
import { AR } from './ar';
import { EN } from './en';
import { FR } from './fr';

export const TRANSLATIONS: Record<LangCode, TranslationMap> = {
  fr: FR,
  en: EN,
  ar: AR,
};

export const LANGUAGE_OPTIONS: { code: LangCode; label: string; menuLabelKey: string }[] = [
  { code: 'fr', label: 'Français', menuLabelKey: 'sidebar.lang.frFR' },
  { code: 'en', label: 'English', menuLabelKey: 'sidebar.lang.enUS' },
  { code: 'ar', label: 'Arabic', menuLabelKey: 'sidebar.lang.ar' },
];
