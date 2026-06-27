const MARKER = '[[GLOBEX_ATTACHMENT:';
const MARKER_END = ']]';

export function unpackMessageText(raw: string): { text: string; imageUrl?: string } {
  if (!raw.startsWith(MARKER)) {
    return { text: raw };
  }
  const end = raw.indexOf(MARKER_END);
  if (end < 0) {
    return { text: raw };
  }
  try {
    const payload = JSON.parse(raw.slice(MARKER.length, end)) as { mime?: string; b64?: string };
    const mime = payload.mime?.trim();
    const b64 = payload.b64?.trim();
    const rest = raw.slice(end + MARKER_END.length).replace(/^\n/, '');
    if (mime && b64) {
      return { text: rest, imageUrl: `data:${mime};base64,${b64}` };
    }
    return { text: rest || raw };
  } catch {
    return { text: raw };
  }
}
