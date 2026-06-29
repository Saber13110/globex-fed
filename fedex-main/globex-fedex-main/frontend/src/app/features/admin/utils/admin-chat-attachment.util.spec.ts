import {
  ALLOWED_ADMIN_ATTACHMENT_MIME,
  MAX_DOCUMENT_BYTES,
  MAX_IMAGE_BYTES,
  attachmentFromClipboardItems,
  isAllowedAdminAttachmentMime,
  maxBytesForAdminAttachment,
} from './admin-chat-attachment.util';

describe('admin-chat-attachment.util', () => {
  describe('isAllowedAdminAttachmentMime', () => {
    it('accepts image and document MIME types', () => {
      expect(isAllowedAdminAttachmentMime('image/png')).toBeTrue();
      expect(isAllowedAdminAttachmentMime('application/pdf')).toBeTrue();
      expect(
        isAllowedAdminAttachmentMime('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
      ).toBeTrue();
    });

    it('rejects unsupported MIME types', () => {
      expect(isAllowedAdminAttachmentMime('text/plain')).toBeFalse();
      expect(isAllowedAdminAttachmentMime('application/zip')).toBeFalse();
    });
  });

  describe('maxBytesForAdminAttachment', () => {
    it('uses image limit for images', () => {
      expect(maxBytesForAdminAttachment('image/jpeg')).toBe(MAX_IMAGE_BYTES);
    });

    it('uses document limit for PDF and Excel', () => {
      expect(maxBytesForAdminAttachment('application/pdf')).toBe(MAX_DOCUMENT_BYTES);
      expect(maxBytesForAdminAttachment('application/vnd.ms-excel')).toBe(MAX_DOCUMENT_BYTES);
    });
  });

  describe('attachmentFromClipboardItems', () => {
    it('returns image file from clipboard items', () => {
      const file = new File(['x'], 'shot.png', { type: 'image/png' });
      const items = {
        length: 1,
        0: { type: 'image/png', getAsFile: () => file },
        [Symbol.iterator]: function* () {
          yield (this as DataTransferItemList)[0];
        },
      } as unknown as DataTransferItemList;

      expect(attachmentFromClipboardItems(items)).toBe(file);
    });

    it('returns PDF file from clipboard items', () => {
      const file = new File(['%PDF'], 'doc.pdf', { type: 'application/pdf' });
      const items = {
        length: 1,
        0: { type: 'application/pdf', getAsFile: () => file },
        [Symbol.iterator]: function* () {
          yield (this as DataTransferItemList)[0];
        },
      } as unknown as DataTransferItemList;

      expect(attachmentFromClipboardItems(items)).toBe(file);
    });

    it('ignores non-image non-PDF clipboard items', () => {
      const items = {
        length: 1,
        0: { type: 'text/plain', getAsFile: () => new File(['hi'], 'a.txt', { type: 'text/plain' }) },
        [Symbol.iterator]: function* () {
          yield (this as DataTransferItemList)[0];
        },
      } as unknown as DataTransferItemList;

      expect(attachmentFromClipboardItems(items)).toBeNull();
    });
  });

  it('exports expected MIME allowlist size', () => {
    expect(ALLOWED_ADMIN_ATTACHMENT_MIME.size).toBe(7);
  });
});
