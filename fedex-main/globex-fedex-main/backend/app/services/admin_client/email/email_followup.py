"""Relances après clarification e-mail admin — récupération contexte suspend+mail."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.admin_client.email.email_patterns import (
    _EMAIL_ADDR_RE,
    _USER_ADMIN_ACTION_RE,
    extract_recipient_email,
    is_users_action_email_combo,
)
from app.services.message_attachment import unpack_message_text

EMAIL_CLARIFY_MARKER_FR = "Quel message souhaitez-vous transmettre"
EMAIL_CLARIFY_MARKER_EN = "What message should I send to the user"
EMAIL_CLARIFY_RECIPIENT_FR = "À qui envoyer l'e-mail"
EMAIL_CLARIFY_RECIPIENT_EN = "Who should receive the email"

_SUSPEND_REASON_RE = re.compile(
    r"\b(?:"
    r"je\s+veux\s+que\s+tu\s+(?:lui\s+)?(?:envoie|envoyer|dis|dire)|"
    r"(?:msg|message)\s+que|dire\s+que|informer\s+que|expliquer\s+que"
    r")\s+(.+)$",
    re.I | re.DOTALL,
)


def _has_clarify_marker(text: str | None) -> bool:
    blob = text or ""
    return any(
        m in blob
        for m in (
            EMAIL_CLARIFY_MARKER_FR,
            EMAIL_CLARIFY_MARKER_EN,
            EMAIL_CLARIFY_RECIPIENT_FR,
            EMAIL_CLARIFY_RECIPIENT_EN,
        )
    )


def _last_assistant_from_history(conversation_history: list[Any] | None) -> str | None:
    for raw in reversed(conversation_history or []):
        if isinstance(raw, dict):
            role = str(raw.get("role") or "").lower()
            content = str(raw.get("content") or "").strip()
        else:
            role = str(getattr(raw, "role", "") or "").lower()
            content = str(getattr(raw, "content", "") or "").strip()
        if role in ("assistant", "bot") and content:
            return content
    return None


def _recent_bot_texts_by_id(db: Session, session_id: int, *, limit: int = 8) -> list[str]:
    texts: list[str] = []
    for msg in db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.sender == MessageSender.bot.value,
        )
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    ).all():
        text, _, _ = unpack_message_text(msg.message_text or "")
        text = (text or "").strip()
        if text:
            texts.append(text)
    return texts


def latest_clarify_bot_text_from_session(db: Session, session_id: int) -> str | None:
    for text in _recent_bot_texts_by_id(db, session_id, limit=10):
        if _has_clarify_marker(text):
            return text
    return None


def is_email_clarify_pending(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if _has_clarify_marker(history_text):
        return True
    if _has_clarify_marker(_last_assistant_from_history(conversation_history)):
        return True
    if db is not None and chat_session_id is not None:
        return latest_clarify_bot_text_from_session(db, chat_session_id) is not None
    return False


def extract_recipient_from_history(history_text: str) -> str | None:
    emails = _EMAIL_ADDR_RE.findall(history_text or "")
    return emails[0].lower() if emails else None


def extract_admin_note_from_clarify_reply(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""
    m = _SUSPEND_REASON_RE.search(text)
    if m:
        return m.group(1).strip()[:2000]
    if len(text) >= 12:
        return text[:2000]
    return ""


def is_suspend_email_clarify_context(history_text: str) -> bool:
    hist = history_text or ""
    if not _USER_ADMIN_ACTION_RE.search(hist):
        return False
    if not re.search(r"\b(mail|e-mail|email|courriel|envoie|envoyer|notifie)\b", hist, re.I):
        return False
    return bool(_EMAIL_ADDR_RE.search(hist))


def is_email_clarify_followup(
    message: str,
    *,
    history_text: str = "",
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if not is_email_clarify_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return False
    text = (message or "").strip()
    if len(text) < 8:
        return False
    if re.match(r"^(oui|non|yes|no|ok|annule|cancel)\b", text, re.I):
        return False
    return True


def recover_suspend_combo_from_history(history_text: str, message: str) -> dict[str, str] | None:
    """Reconstruit suspend+mail depuis un fil où l'agent e-mail a demandé le message."""
    if not is_suspend_email_clarify_context(history_text):
        return None
    recipient = extract_recipient_from_history(history_text) or extract_recipient_email(history_text)
    if not recipient:
        return None
    reason = extract_admin_note_from_clarify_reply(message)
    return {"recipient_email": recipient, "suspend_reason": reason, "notify_email": "true"}
