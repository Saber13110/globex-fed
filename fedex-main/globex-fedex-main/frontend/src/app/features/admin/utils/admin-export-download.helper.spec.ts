import { of, throwError } from 'rxjs';

import { AdminAiService, AdminExportDownloadSpec } from '../../../core/services/admin-ai.service';
import { HistoryService } from '../../../core/services/history.service';
import {
  downloadAdminExport,
  isClientPipelineExport,
  toExportDownloadSpec,
} from './admin-export-download.helper';

describe('isClientPipelineExport', () => {
  it('returns false for admin_logs', () => {
    expect(
      isClientPipelineExport({ preset: 'admin_logs', filename: 'logs.pdf' }),
    ).toBeFalse();
  });

  it('returns false for admin_tracking with export_token', () => {
    expect(
      isClientPipelineExport({
        preset: 'admin_tracking',
        filename: 't.xlsx',
        export_token: 'tok12345678',
      }),
    ).toBeFalse();
  });

  it('returns true for text_pdf with export_token', () => {
    expect(
      isClientPipelineExport({
        preset: 'text_pdf',
        filename: 'doc.pdf',
        export_token: 'tok12345678',
      }),
    ).toBeTrue();
  });

  it('returns true for text_xlsx with export_token', () => {
    expect(
      isClientPipelineExport({
        preset: 'text_xlsx',
        filename: 'doc.xlsx',
        export_token: 'tok12345678',
      }),
    ).toBeTrue();
  });

  it('returns true for tracking preset without token', () => {
    expect(
      isClientPipelineExport({
        preset: 'tracking',
        filename: 'hist.pdf',
        session_id: 42,
      }),
    ).toBeTrue();
  });
});

describe('toExportDownloadSpec', () => {
  it('splits comma-separated tracking numbers', () => {
    const mapped = toExportDownloadSpec({
      preset: 'tracking',
      filename: 'hist.pdf',
      tracking_numbers: '123, 456',
      session_id: 7,
    });
    expect(mapped.tracking_numbers).toEqual(['123', '456']);
    expect(mapped.session_id).toBe(7);
  });

  it('keeps tracking number array', () => {
    const mapped = toExportDownloadSpec({
      preset: 'tracking',
      filename: 'hist.xlsx',
      tracking_numbers: ['817950452196'],
      session_id: 3,
      include_events: false,
    });
    expect(mapped.tracking_numbers).toEqual(['817950452196']);
    expect(mapped.include_events).toBeFalse();
  });
});

describe('downloadAdminExport client pipeline delegation', () => {
  it('calls HistoryService.downloadFromSpec for text_pdf', () => {
    const api = jasmine.createSpyObj<AdminAiService>('AdminAiService', [
      'downloadActivityLogsPdf',
      'downloadContextPdf',
    ]);
    const history = jasmine.createSpyObj<HistoryService>('HistoryService', ['downloadFromSpec']);
    history.downloadFromSpec.and.returnValue(of(new Blob(['pdf'])));

    const spec: AdminExportDownloadSpec = {
      preset: 'text_pdf',
      filename: 'rapport.pdf',
      export_token: 'tok12345678',
      session_id: 12,
    };

    downloadAdminExport(api, spec, () => {}, { history, lang: 'fr' });

    expect(history.downloadFromSpec).toHaveBeenCalled();
    const [mapped, lang] = history.downloadFromSpec.calls.mostRecent().args;
    expect(mapped.export_token).toBe('tok12345678');
    expect(mapped.preset).toBe('text_pdf');
    expect(lang).toBe('fr');
    expect(api.downloadActivityLogsPdf).not.toHaveBeenCalled();
  });

  it('still uses AdminAiService for admin_logs', () => {
    const api = jasmine.createSpyObj<AdminAiService>('AdminAiService', ['downloadActivityLogsPdf']);
    api.downloadActivityLogsPdf.and.returnValue(of(new Blob(['pdf'])));
    const history = jasmine.createSpyObj<HistoryService>('HistoryService', ['downloadFromSpec']);

    downloadAdminExport(
      api,
      { preset: 'admin_logs', filename: 'logs.pdf', hours: 24 },
      () => {},
      { history, lang: 'fr' },
    );

    expect(api.downloadActivityLogsPdf).toHaveBeenCalled();
    expect(history.downloadFromSpec).not.toHaveBeenCalled();
  });

  it('invokes onError when client download fails', () => {
    const api = jasmine.createSpyObj<AdminAiService>('AdminAiService', ['downloadActivityLogsPdf']);
    const history = jasmine.createSpyObj<HistoryService>('HistoryService', ['downloadFromSpec']);
    history.downloadFromSpec.and.returnValue(throwError(() => new Error('fail')));
    let errMsg = '';
    const spec: AdminExportDownloadSpec = {
      preset: 'text_xlsx',
      filename: 'suivi.xlsx',
      export_token: 'tok12345678',
    };

    downloadAdminExport(api, spec, (msg) => (errMsg = msg), { history, lang: 'en' });

    expect(errMsg).toBe('Échec du téléchargement.');
  });
});
