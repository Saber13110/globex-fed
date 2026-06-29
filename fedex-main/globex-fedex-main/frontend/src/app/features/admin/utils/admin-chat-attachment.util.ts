export const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;

export const ALLOWED_ADMIN_ATTACHMENT_MIME = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
]);

export interface AdminChatAttachment {
  base64: string;
  mime: string;
  name: string;
  isImage: boolean;
}

export type AdminAttachmentReadError = 'format' | 'size';

export type AdminAttachmentReadResult =
  | { ok: true; attachment: AdminChatAttachment }
  | { ok: false; error: AdminAttachmentReadError };

export function isAllowedAdminAttachmentMime(mime: string): boolean {
  return ALLOWED_ADMIN_ATTACHMENT_MIME.has(mime);
}

export function maxBytesForAdminAttachment(mime: string): number {
  return mime.startsWith('image/') ? MAX_IMAGE_BYTES : MAX_DOCUMENT_BYTES;
}

export function attachmentFromClipboardItems(items: DataTransferItemList): File | null {
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/') || item.type === 'application/pdf') {
      const file = item.getAsFile();
      if (file) {
        return file;
      }
    }
  }
  return null;
}

export function readAttachmentFile(file: File): Promise<AdminAttachmentReadResult> {
  if (!isAllowedAdminAttachmentMime(file.type)) {
    return Promise.resolve({ ok: false, error: 'format' });
  }
  const isImage = file.type.startsWith('image/');
  const maxBytes = maxBytesForAdminAttachment(file.type);
  if (file.size > maxBytes) {
    return Promise.resolve({ ok: false, error: 'size' });
  }

  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string') {
        resolve({ ok: false, error: 'format' });
        return;
      }
      const comma = result.indexOf(',');
      const base64 = comma >= 0 ? result.slice(comma + 1) : '';
      if (!base64) {
        resolve({ ok: false, error: 'format' });
        return;
      }
      resolve({
        ok: true,
        attachment: { base64, mime: file.type, name: file.name, isImage },
      });
    };
    reader.onerror = () => resolve({ ok: false, error: 'format' });
    reader.readAsDataURL(file);
  });
}
