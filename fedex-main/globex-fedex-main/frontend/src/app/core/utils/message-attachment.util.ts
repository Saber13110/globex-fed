const MARKER = '[[GLOBEX_ATTACHMENT:';
const MARKER_END = ']]';

export function unpackMessageText(raw: string): {
  text: string;
  imageUrl?: string;
  fileName?: string;
  isDocument?: boolean;
} {
  if (!raw.startsWith(MARKER)) {
    return { text: raw };
  }
  const end = raw.indexOf(MARKER_END);
  if (end < 0) {
    return { text: raw };
  }
  try {
    const payload = JSON.parse(raw.slice(MARKER.length, end)) as {
      mime?: string;
      b64?: string;
      name?: string;
      kind?: string;
    };
    const mime = payload.mime?.trim();
    const b64 = payload.b64?.trim();
    const rest = raw.slice(end + MARKER_END.length).replace(/^\n/, '');
    const fileName = payload.name?.trim() || undefined;
    const kind = payload.kind?.trim();
    const isDocument = kind === 'document' || (mime ? !mime.startsWith('image/') : false);
    if (mime && b64) {
      if (isDocument) {
        return { text: rest, fileName, isDocument: true };
      }
      return { text: rest, imageUrl: `data:${mime};base64,${b64}`, fileName };
    }
    return { text: rest || raw };
  } catch {
    return { text: raw };
  }
}
