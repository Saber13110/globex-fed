export type CopilotFileKind = 'image' | 'pdf' | 'excel' | 'word' | 'text' | 'other';

export interface PendingCopilotFile {
  file: File;
  name: string;
  kind: CopilotFileKind;
  mimeType: string;
  previewUrl?: string;
  imageBase64?: string;
}

export const COPILOT_ALLOWED_EXTENSIONS = new Set([
  'pdf', 'docx', 'xlsx', 'xls', 'txt', 'md', 'csv',
  'jpg', 'jpeg', 'png', 'webp', 'gif',
]);

export const MAX_COPILOT_FILE_BYTES = 15 * 1024 * 1024;

export function copilotFileKind(filename: string, mimeType: string): CopilotFileKind {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  if (['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(ext) || mimeType.startsWith('image/')) {
    return 'image';
  }
  if (['xlsx', 'xls'].includes(ext)) return 'excel';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'docx') return 'word';
  if (['txt', 'md', 'csv'].includes(ext)) return 'text';
  return 'other';
}

export function copilotFileIcon(kind: CopilotFileKind): string {
  switch (kind) {
    case 'image': return '🖼️';
    case 'pdf': return '📄';
    case 'excel': return '📊';
    case 'word': return '📝';
    case 'text': return '📃';
    default: return '📎';
  }
}
