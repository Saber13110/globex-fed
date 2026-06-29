"""Suite de dialogue Security IDS — relances après liste incidents."""

from __future__ import annotations

import re

_SECURITY_HISTORY_MARKERS = re.compile(
    r"Incidents s[eé]curit[eé]|Security incidents|Liste des incidents|"
    r"Fiche incident|Incident detail|Rapport s[eé]curit[eé]|"
    r"\| S[eé]v[eé]rit[eé] \| Menace \|",
    re.I,
)

_FOLLOWUP_ACTION_RE = re.compile(
    r"\b("
    r"d[eé]tail|fiche|infos?|consulte|montre|affiche|"
    r"ouvr|incident|"
    r"r[eé]sum[eé]|summary|rapport"
    r")\b",
    re.I,
)

_INCIDENT_HASH_RE = re.compile(r"\bincident\s*#\s*(\d{1,8})\b", re.I)
_INCIDENT_REF_RE = re.compile(r"\bincident\s*#?\s*(\d{1,8})\b", re.I)
_INCIDENT_BARE_HASH_RE = re.compile(r"#\s*(\d{1,8})\b", re.I)
_INCIDENT_LE_RE = re.compile(r"\b(?:le|la|num[eé]ro|n°)\s*#?\s*(\d{1,8})\b", re.I)
_LIST_ROW_RE = re.compile(r"\|\s*#?(\d{1,8})\s*\|", re.MULTILINE)


def list_incident_ids_from_history(history_text: str) -> list[int]:
    ids: list[int] = []
    for m in _LIST_ROW_RE.finditer(history_text or ""):
        iid = int(m.group(1))
        if iid not in ids:
            ids.append(iid)
    return ids


def is_security_history_context(history_text: str) -> bool:
    return bool(_SECURITY_HISTORY_MARKERS.search(history_text or ""))


def has_incidents_list_data(history_text: str) -> bool:
    hist = history_text or ""
    if is_security_history_context(hist):
        return True
    return len(list_incident_ids_from_history(hist)) >= 2


def merge_security_history_text(
    db,
    session,
    user_msg_id: int,
    *,
    history_text: str | None = None,
    conversation_history: list | None = None,
) -> str:
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
            if has_incidents_list_data(text) or re.search(r"Fiche incident", text or "", re.I):
                _append(text)
                break

        from app.services.chat_session_context import build_conversation_history_for_llm

        db_hist = build_conversation_history_for_llm(
            db, session_id=session_id, exclude_message_id=user_msg_id, limit=12
        )
        from app.services.admin_client.pipeline import _history_text

        _append(_history_text(db_hist))

    return "\n".join(chunks)


def extract_list_row_index(message: str) -> int | None:
    text = (message or "").strip()
    m = re.search(
        r"\b(\d{1,2})\s*(?:er|ere|eme|ème|e)(?:\s+incident)?\b",
        text,
        re.I,
    )
    if m:
        return int(m.group(1)) - 1
    if re.search(r"\b(premier|premiere|first|1er|1ere|1ère)\b", text, re.I):
        return 0
    if re.search(r"\b(second|deuxieme|deuxième|2eme|2ème)\b", text, re.I):
        return 1
    return None


def _resolve_ref_from_list_row(ref: int, history_text: str) -> int | None:
    ids = list_incident_ids_from_history(history_text)
    if ids and 1 <= ref <= len(ids):
        return ids[ref - 1]
    return None


def _resolve_explicit_incident_id(n: int, history_text: str) -> int | None:
    """`incident #N` → ID colonne N si présent dans la liste visible."""
    ids = list_incident_ids_from_history(history_text)
    if n in ids:
        return n
    return None


def extract_incident_ref(message: str, *, history_text: str = "") -> int | None:
    text = (message or "").strip()
    if not text:
        return None

    from app.services.admin_client.security.security_patterns import message_targets_incidents

    if re.search(r"\blog\b", text, re.I) and not message_targets_incidents(text):
        return None

    list_ctx = has_incidents_list_data(history_text)

    if list_ctx:
        idx = extract_list_row_index(text)
        if idx is not None:
            ids = list_incident_ids_from_history(history_text)
            if 0 <= idx < len(ids):
                return ids[idx]

    m_hash = _INCIDENT_HASH_RE.search(text)
    if m_hash:
        n = int(m_hash.group(1))
        if list_ctx:
            explicit = _resolve_explicit_incident_id(n, history_text)
            if explicit is not None:
                return explicit
            row_id = _resolve_ref_from_list_row(n, history_text)
            if row_id is not None:
                return row_id
        return n

    for pattern in (_INCIDENT_REF_RE,):
        m = pattern.search(text)
        if m:
            n = int(m.group(1))
            if list_ctx:
                explicit = _resolve_explicit_incident_id(n, history_text)
                if explicit is not None:
                    return explicit
                row_id = _resolve_ref_from_list_row(n, history_text)
                if row_id is not None:
                    return row_id
            return n

    if list_ctx and message_targets_incidents(text):
        m = _INCIDENT_BARE_HASH_RE.search(text)
        if m:
            n = int(m.group(1))
            row_id = _resolve_ref_from_list_row(n, history_text)
            if row_id is not None:
                return row_id
            ids = list_incident_ids_from_history(history_text)
            if n in ids:
                return n
            return n

    if list_ctx and message_targets_incidents(text):
        m = _INCIDENT_LE_RE.search(text)
        if m:
            n = int(m.group(1))
            row_id = _resolve_ref_from_list_row(n, history_text)
            if row_id is not None:
                return row_id
            return n
    return None


def resolve_incident_id_from_context(
    db,
    ref: int,
    *,
    history_text: str = "",
    prefer_row: bool = False,
) -> int | None:
    from app.models.security_incident import SecurityIncident

    if has_incidents_list_data(history_text):
        ids = list_incident_ids_from_history(history_text)
        if not prefer_row and ref in ids and db.get(SecurityIncident, ref):
            return ref
        if ids and 1 <= ref <= len(ids):
            row_id = ids[ref - 1]
            if db.get(SecurityIncident, row_id):
                return row_id
        if ref in ids and db.get(SecurityIncident, ref):
            return ref
    if db.get(SecurityIncident, ref):
        return ref
    return None


def format_incident_ids_hint(history_text: str, *, lang: str = "fr") -> str:
    ids = list_incident_ids_from_history(history_text)
    if not ids:
        return ""
    shown = ", ".join(f"#{i}" for i in ids[:10])
    if lang == "en":
        return (
            f" Recent list IDs: {shown}. "
            f"« #1 » usually means row 1 in that list."
        )
    return (
        f" IDs visibles : {shown}. "
        f"« incident #id » = ID en base ; « le N » ou « #N » seul = Nᵉ ligne du tableau."
    )


def is_security_followup_message(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text or not has_incidents_list_data(history_text):
        return False
    if extract_incident_ref(text, history_text=history_text) is not None:
        return True
    if extract_list_row_index(text) is not None and re.search(r"\bincident", text, re.I):
        return True
    return bool(_FOLLOWUP_ACTION_RE.search(text))


def extract_focus_incident_from_history(history_text: str) -> int | None:
    hist = history_text or ""
    m = re.search(r"Fiche incident[^\n]*\n+#(\d{1,8})\b", hist, re.I)
    if m:
        return int(m.group(1))
    return extract_incident_ref(hist, history_text=hist)
