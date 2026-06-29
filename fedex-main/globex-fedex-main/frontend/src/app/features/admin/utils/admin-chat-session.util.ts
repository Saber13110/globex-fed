/** Session miroir admin_client partagée entre sidebar, fenêtre agent et FEDEX-V0. */
export const GLOBEX_ADMIN_CHAT_SESSION_KEY = 'globex_admin_chat_session_id';

export function readPersistedAdminChatSessionId(): number | null {
  try {
    const raw = localStorage.getItem(GLOBEX_ADMIN_CHAT_SESSION_KEY);
    if (!raw) {
      return null;
    }
    const id = parseInt(raw, 10);
    return Number.isFinite(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function persistAdminChatSessionId(id: number | null | undefined): void {
  try {
    if (id != null && id > 0) {
      localStorage.setItem(GLOBEX_ADMIN_CHAT_SESSION_KEY, String(id));
    }
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearPersistedAdminChatSessionId(): void {
  try {
    localStorage.removeItem(GLOBEX_ADMIN_CHAT_SESSION_KEY);
  } catch {
    /* ignore */
  }
}
