import { AdminAiService, AdminExportDownloadSpec } from '../../../core/services/admin-ai.service';
import { ExportDownloadSpec } from '../../../core/services/chatbot.service';
import { ExportLang, HistoryService } from '../../../core/services/history.service';

const CLIENT_PIPELINE_PRESETS = new Set([
  'text_pdf',
  'text_xlsx',
  'notifications_pdf',
  'tracking',
  'tracking_summary',
  'pod',
]);

function trackingNumbersAsString(raw: string | string[] | undefined): string {
  if (Array.isArray(raw)) {
    return raw.map((n) => n.trim()).filter(Boolean).join(',');
  }
  return (raw ?? '').trim();
}

function trackingNumbersAsArray(raw: string | string[] | undefined): string[] {
  if (Array.isArray(raw)) {
    return raw.map((n) => n.trim()).filter(Boolean);
  }
  if (!raw?.trim()) {
    return [];
  }
  return raw
    .split(',')
    .map((n) => n.trim())
    .filter(Boolean);
}

/** Export généré par le pipeline admin_client (presets client, pas admin_*). */
export function isClientPipelineExport(spec: AdminExportDownloadSpec): boolean {
  const preset = (spec.preset ?? '').toLowerCase();
  if (preset.startsWith('admin_')) {
    return false;
  }
  if (spec.export_token?.trim()) {
    return true;
  }
  return CLIENT_PIPELINE_PRESETS.has(preset);
}

/** Mappe la spec admin vers le format attendu par HistoryService.downloadFromSpec. */
export function toExportDownloadSpec(spec: AdminExportDownloadSpec): ExportDownloadSpec {
  return {
    session_id: spec.session_id ?? 0,
    tracking_numbers: trackingNumbersAsArray(spec.tracking_numbers),
    preset: spec.preset,
    include_events: spec.include_events ?? true,
    export_token: spec.export_token ?? null,
    filename: spec.filename ?? null,
    format: spec.format ?? null,
  };
}

export interface AdminClientExportContext {
  history: HistoryService;
  lang?: ExportLang;
}

/** Téléchargement export admin — même logique que admin-ai-assistant (sans modifier ce composant). */
export function downloadAdminExport(
  api: AdminAiService,
  spec: AdminExportDownloadSpec,
  onError: (msg: string) => void,
  clientExport?: AdminClientExportContext,
): void {
  if (spec.preset === 'admin_platform_report') {
    api.downloadPlatformReportPdf(spec.hours ?? 24, spec.filename ?? 'platform-report.pdf').subscribe({
      error: () => onError('Échec du téléchargement rapport.'),
    });
    return;
  }
  if (spec.preset === 'admin_tracking') {
    const numbers = trackingNumbersAsString(spec.tracking_numbers);
    const fmt =
      spec.format ??
      (spec.filename?.endsWith('.xlsx') ? 'xlsx' : spec.filename?.endsWith('.csv') ? 'csv' : 'pdf');
    if (numbers && fmt === 'pdf') {
      api.downloadTrackingStatusPdf(numbers, spec.filename ?? 'tracking-status.pdf').subscribe({
        error: () => onError('Échec du téléchargement PDF tracking.'),
      });
      return;
    }
    if (fmt === 'xlsx' && spec.export_token) {
      api
        .downloadContextXlsx(spec.preset, spec.export_token, spec.filename ?? 'tracking-export.xlsx')
        .subscribe({ error: () => onError('Échec du téléchargement Excel tracking.') });
      return;
    }
    api
      .downloadContextPdf(
        spec.preset,
        spec.limit ?? spec.records ?? 10,
        spec.filename ?? 'tracking-export.pdf',
        spec.module,
        spec.export_token,
      )
      .subscribe({ error: () => onError('Échec du téléchargement PDF tracking.') });
    return;
  }
  const contextPresets = new Set([
    'admin_notifications',
    'admin_users',
    'admin_tickets',
    'admin_conversations',
    'admin_generic',
    'admin_security',
  ]);
  if (contextPresets.has(spec.preset)) {
    api
      .downloadContextPdf(
        spec.preset,
        spec.limit ?? spec.records ?? 10,
        spec.filename ?? 'export.pdf',
        spec.module,
        spec.export_token,
      )
      .subscribe({ error: () => onError('Échec du téléchargement PDF.') });
    return;
  }
  if (spec.preset !== 'admin_logs') {
    if (clientExport && isClientPipelineExport(spec)) {
      clientExport.history
        .downloadFromSpec(toExportDownloadSpec(spec), clientExport.lang ?? 'fr')
        .subscribe({ error: () => onError('Échec du téléchargement.') });
    }
    return;
  }
  const hours = spec.hours ?? 24;
  const fmt =
    spec.format ??
    (spec.filename?.endsWith('.xlsx') ? 'xlsx' : spec.filename?.endsWith('.csv') ? 'csv' : 'pdf');
  if (fmt === 'xlsx') {
    api.downloadActivityLogsExcel(hours, spec.filename ?? 'activity-logs.xlsx').subscribe({
      error: () => onError('Échec du téléchargement Excel.'),
    });
    return;
  }
  if (fmt === 'csv') {
    api.downloadActivityLogsCsv(hours, spec.filename ?? 'activity-logs.csv').subscribe({
      error: () => onError('Échec du téléchargement CSV.'),
    });
    return;
  }
  api.downloadActivityLogsPdf(hours, spec.filename ?? 'activity-logs.pdf').subscribe({
    error: () => onError('Échec du téléchargement PDF.'),
  });
}
