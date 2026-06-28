import {
  buildDocumentDownloadSpec,
  classifyDocumentBlob,
} from './document-catalog.util';

describe('document-catalog.util', () => {
  it('classifies rapport du jour as report', () => {
    expect(classifyDocumentBlob('envoie moi le rapport du jour')).toBe('report');
  });

  it('classifies export historique as export', () => {
    expect(classifyDocumentBlob('Export historique FedEx')).toBe('export');
  });

  it('builds pdf spec for report type', () => {
    const spec = buildDocumentDownloadSpec({
      type: 'report',
      sessionId: 42,
      sourceText: 'envoie moi le rapport du jour',
    });
    expect(spec.format).toBe('pdf');
    expect(spec.preset).toBe('tracking');
  });

  it('builds xlsx spec for export type', () => {
    const spec = buildDocumentDownloadSpec({
      type: 'export',
      trackingNumber: '880892017122',
      sessionId: 5,
    });
    expect(spec.format).toBe('xlsx');
  });
});
