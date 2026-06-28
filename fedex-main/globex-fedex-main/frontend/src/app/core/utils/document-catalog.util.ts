import { ExportDownloadSpec } from '../services/chatbot.service';

export type DocumentCatalogType = 'export' | 'proof' | 'report';

export interface DocumentDownloadInput {
  type: DocumentCatalogType;
  trackingNumber?: string;
  sessionId?: number;
  title?: string;
  sourceText?: string;
}

const PROOF_RE = /\b(preuve|proof|pod|livraison|delivery)\b/i;
const EXCEL_RE = /\b(excel|xlsx|\.xlsx)\b/i;
const REPORT_RE = /\b(rapport|report|pdf|document|facture|invoice)\b/i;
const EXPORT_WORD_RE = /\bexport\b/i;
const EXCEL_HINT_RE = /\b(xlsx|excel|\.xlsx)\b/i;
const PDF_HINT_RE = /\b(pdf|text_pdf|\.pdf)\b/i;

export function classifyDocumentBlob(text: string): DocumentCatalogType | null {
  const blob = (text || '').toLowerCase();
  if (PROOF_RE.test(blob)) {
    return 'proof';
  }
  if (EXCEL_RE.test(blob)) {
    return 'export';
  }
  if (REPORT_RE.test(blob)) {
    return 'report';
  }
  if (EXPORT_WORD_RE.test(blob)) {
    return 'export';
  }
  return null;
}

function formatFromSourceText(sourceText?: string): 'xlsx' | 'pdf' | null {
  const blob = (sourceText || '').toLowerCase();
  if (EXCEL_HINT_RE.test(blob)) {
    return 'xlsx';
  }
  if (PDF_HINT_RE.test(blob)) {
    return 'pdf';
  }
  return null;
}

export function buildDocumentDownloadSpec(doc: DocumentDownloadInput): ExportDownloadSpec {
  const tn = (doc.trackingNumber || '').trim();
  const trackingNumbers = tn ? [tn] : [];
  const sessionId = doc.sessionId ?? 0;

  if (doc.type === 'proof') {
    return {
      session_id: sessionId,
      tracking_numbers: trackingNumbers,
      preset: 'pod',
      include_events: true,
      filename: tn ? `preuve-livraison-${tn}.pdf` : 'preuve-livraison.pdf',
      format: 'pdf',
    };
  }

  const fmtHint = formatFromSourceText(doc.sourceText ?? doc.title);
  const useXlsx = fmtHint === 'xlsx' || (fmtHint === null && doc.type === 'export');

  if (useXlsx) {
    return {
      session_id: sessionId,
      tracking_numbers: trackingNumbers,
      preset: 'tracking',
      include_events: false,
      filename: tn ? `export-${tn}.xlsx` : 'tracking-export.xlsx',
      format: 'xlsx',
    };
  }

  return {
    session_id: sessionId,
    tracking_numbers: trackingNumbers,
    preset: 'tracking',
    include_events: true,
    filename: tn ? `rapport-${tn}.pdf` : 'historique-suivi.pdf',
    format: 'pdf',
  };
}
