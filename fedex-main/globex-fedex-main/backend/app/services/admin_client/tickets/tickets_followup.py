"""Suite de dialogue tickets support — relances après liste."""

from __future__ import annotations

import re

_TICKETS_HISTORY_MARKERS = re.compile(
    r"Liste des tickets|Ticket list|Tickets support|Support tickets|"
    r"R[eé]sum[eé] des tickets|Ticket summary|"
    r"D[eé]tails des tickets|Ticket details batch|"
    r"Fiche ticket|Ticket detail",
    re.I,
)

_FOLLOWUP_ACTION_RE = re.compile(
    r"\b("
    r"d[eé]tail|fiche|infos?|consulte|montre|affiche|"
    r"messages?|conversation|fil|thread|"
    r"r[eé]pond|repond|reply|r[eé]ponse|"
    r"r[eé]solu|resolu|resolve|ferm|close"
    r")\b",
    re.I,
)

_TICKET_HASH_RE = re.compile(r"\bticket\s*#\s*(\d{1,8})\b", re.I)
_TICKET_BARE_HASH_RE = re.compile(r"#\s*(\d{1,8})\b", re.I)
_TICKET_REF_RE = re.compile(r"\bticket\s*#?\s*(\d{1,8})\b", re.I)
_TICKET_LE_RE = re.compile(r"\b(?:le|la|num[eé]ro|n°)\s*#?\s*(\d{1,8})\b", re.I)
_ORDINAL_TICKET_RE = re.compile(
    r"\b(?:le\s+)?(\d{1,2})(?:er|ere|eme|ème|e)(?:\s+ticket)?\b|"
    r"\b(premier|premiere|first|second|deuxieme|deuxième|2eme|2ème)\b",
    re.I,
)
_TKT_NUM_RE = re.compile(r"\b(TKT[-_]?|SUP-)\w+\b", re.I)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_LIST_ROW_RE = re.compile(r"\|\s*#?(\d{1,8})\s*\|", re.MULTILINE)
_FICHE_TICKET_ID_RE = re.compile(r"Fiche ticket[^\n]*\n+#(\d{1,8})\b", re.I)
_LOGS_LIST_MARKER = re.compile(
    r"Journal d.?activit[eé]|Activity log|\| Date \| Niveau \| Action \|",
    re.I,
)
_INCIDENTS_LIST_MARKER = re.compile(
    r"Incidents s[eé]curit[eé]|Security incidents|\| S[eé]v[eé]rit[eé] \| Menace \|",
    re.I,
)


def _message_targets_logs(message: str) -> bool:
    """True si l'utilisateur parle explicitement d'un log/journal (pas ticket)."""
    text = message or ""
    if re.search(r"\b(logs?|journaux?|journal)\b", text, re.I):
        return True
    if re.search(r"\blog\b", text, re.I) and not re.search(r"\bticket", text, re.I):
        return True
    return False


def _message_targets_incidents(message: str) -> bool:
    from app.services.admin_client.security.security_patterns import message_targets_incidents

    return message_targets_incidents(message)


def list_ticket_ids_from_history(history_text: str) -> list[int]:
    ids: list[int] = []
    for m in _LIST_ROW_RE.finditer(history_text or ""):
        tid = int(m.group(1))
        if tid not in ids:
            ids.append(tid)
    return ids


def has_tickets_list_data(history_text: str) -> bool:
    """Liste tickets dans le fil — pas confondre avec le journal d'activité."""
    hist = history_text or ""
    if _LOGS_LIST_MARKER.search(hist):
        return False
    if _INCIDENTS_LIST_MARKER.search(hist):
        return False
    if is_tickets_history_context(hist):
        return True
    return len(list_ticket_ids_from_history(hist)) >= 2


def merge_tickets_history_text(
    db,
    session,
    user_msg_id: int,
    *,
    history_text: str | None = None,
    conversation_history: list | None = None,
) -> str:
    """Historique fusionné — payload client + messages bot session DB."""
    chunks: list[str] = []

    def _append(text: str) -> None:
        t = (text or "").strip()
        if t and t not in chunks:
            chunks.append(t)

    _append(history_text or "")
    if conversation_history:
        from app.services.admin_client.pipeline import _history_text

        _append(_history_text(conversation_history))

    session_id = getattr(session, "id", None)
    if db is not None and session_id:
        from sqlalchemy import select

        from app.models.chat_message import ChatMessage, MessageSender
        from app.services.message_attachment import unpack_message_text

        for msg in db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.sender == MessageSender.bot.value,
            )
            .order_by(ChatMessage.id.desc())
            .limit(12)
        ).all():
            text, _, _ = unpack_message_text(msg.message_text or "")
            if has_tickets_list_data(text) or _FICHE_TICKET_ID_RE.search(text or ""):
                _append(text)
                break

        from app.services.chat_session_context import build_conversation_history_for_llm

        db_hist = build_conversation_history_for_llm(
            db, session_id=session_id, exclude_message_id=user_msg_id, limit=12
        )
        from app.services.admin_client.pipeline import _history_text

        _append(_history_text(db_hist))

    return "\n".join(chunks)


def is_tickets_history_context(history_text: str) -> bool:
    return bool(_TICKETS_HISTORY_MARKERS.search(history_text or ""))


def is_tickets_followup_message(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text or _message_targets_logs(text) or _message_targets_incidents(text):
        return False
    if not has_tickets_list_data(history_text):
        return False
    if extract_ticket_ref(text, history_text=history_text) is not None:
        return True
    if _TKT_NUM_RE.search(text):
        return True
    if _ORDINAL_TICKET_RE.search(text):
        return True
    if _EMAIL_RE.search(text) and re.search(r"\btickets?\b", text, re.I):
        return True
    return bool(_FOLLOWUP_ACTION_RE.search(text))


def extract_email_from_message(message: str) -> str | None:
    m = _EMAIL_RE.search(message or "")
    return m.group(0) if m else None


def extract_list_row_index(message: str) -> int | None:
    """Index 0-based dans la dernière liste (1er ticket → 0, 2eme → 1)."""
    text = (message or "").strip()
    m = re.search(
        r"\b(\d{1,2})\s*(?:er|ere|eme|ème|e)(?:\s+ticket)?\b",
        text,
        re.I,
    )
    if m:
        return int(m.group(1)) - 1
    if re.search(r"\b(premier|premiere|first|1er|1ere|1ère)\b", text, re.I):
        return 0
    if re.search(r"\b(second|deuxieme|deuxième|2eme|2ème|2eme)\b", text, re.I):
        return 1
    if re.search(r"\b(troisieme|troisième|third|3eme|3ème)\b", text, re.I):
        return 2
    return None


def _resolve_ref_from_list_row(ref: int, history_text: str) -> int | None:
    ids = list_ticket_ids_from_history(history_text)
    if ids and 1 <= ref <= len(ids):
        return ids[ref - 1]
    return None


def extract_ticket_ref(message: str, *, history_text: str = "") -> int | None:
    text = (message or "").strip()
    if not text:
        return None

    if _message_targets_logs(text):
        return None

    if _message_targets_incidents(text):
        return None

    list_ctx = has_tickets_list_data(history_text)

    if list_ctx:
        idx = extract_list_row_index(text)
        if idx is not None:
            ids = list_ticket_ids_from_history(history_text)
            if 0 <= idx < len(ids):
                return ids[idx]

    for pattern in (_TICKET_HASH_RE, _TICKET_REF_RE):
        m = pattern.search(text)
        if m:
            n = int(m.group(1))
            if list_ctx:
                row_id = _resolve_ref_from_list_row(n, history_text)
                if row_id is not None:
                    return row_id
            return n

    if list_ctx and not _message_targets_logs(text):
        m = _TICKET_BARE_HASH_RE.search(text)
        if m:
            n = int(m.group(1))
            row_id = _resolve_ref_from_list_row(n, history_text)
            if row_id is not None:
                return row_id
            return n

    if list_ctx:
        m = _TICKET_LE_RE.search(text)
        if m:
            n = int(m.group(1))
            row_id = _resolve_ref_from_list_row(n, history_text)
            if row_id is not None:
                return row_id
            return n
    return None


def resolve_ticket_id_from_context(
    db,
    ref: int,
    *,
    history_text: str = "",
) -> int | None:
    """Ligne du tableau en priorité si liste récente, sinon id PostgreSQL."""
    from app.models.support_ticket import SupportTicket

    if has_tickets_list_data(history_text):
        row_id = _resolve_ref_from_list_row(ref, history_text)
        if row_id is not None and db.get(SupportTicket, row_id):
            return row_id

    if db.get(SupportTicket, ref):
        return ref
    return None


def format_ticket_ids_hint(history_text: str, *, lang: str = "fr") -> str:
    ids = list_ticket_ids_from_history(history_text)
    if not ids:
        return ""
    shown = ", ".join(f"#{i}" for i in ids[:10])
    if lang == "en":
        return (
            f" Recent list IDs: {shown}. "
            f"« #1 » usually means row 1 in that list (not necessarily database id 1)."
        )
    return (
        f" IDs visibles dans la liste : {shown}. "
        f"« #1 » désigne en général la **1ère ligne** du tableau (pas forcément l'id 1 en base)."
    )


def extract_ticket_number_token(message: str) -> str | None:
    m = _TKT_NUM_RE.search(message or "")
    return m.group(0) if m else None
