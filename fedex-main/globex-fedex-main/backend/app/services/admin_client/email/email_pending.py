"""Confirmation chat envoi e-mail utilisateur."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.admin_client.email.email_types import PendingEmailAction
from app.services.message_attachment import unpack_message_text

EMAIL_CONFIRM_MARKER_FR = "Répondez par oui ou non pour confirmer l'envoi de cet e-mail"
EMAIL_CONFIRM_MARKER_EN = "Reply yes or no to confirm sending this email"

_PENDING_RE = re.compile(
    r"\[ADMIN_EMAIL_PENDING\s+(\{.*?\})\]",
    re.DOTALL,
)
_CONFIRM_RE = re.compile(r"^(oui|confirme|yes|ok|confirmer|envoie|envoyer)\b", re.I)
_CANCEL_RE = re.compile(r"^(non|annule|annuler|cancel|no)\b", re.I)


def build_email_pending_marker(
    *,
    to: str,
    subject: str,
    body_text: str,
    user_id: int | None = None,
    attachment_export_token: str | None = None,
) -> str:
    payload = {
        "to": to,
        "subject": subject,
        "body_text": body_text,
        "user_id": user_id,
        "attachment_export_token": attachment_export_token,
    }
    blob = json.dumps(payload, ensure_ascii=False)
    return f"\n\n[ADMIN_EMAIL_PENDING {blob}]"


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


def _has_email_marker(text: str | None) -> bool:
    blob = text or ""
    return (
        EMAIL_CONFIRM_MARKER_FR in blob
        or EMAIL_CONFIRM_MARKER_EN in blob
        or bool(_PENDING_RE.search(blob))
    )


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


def latest_pending_bot_text_from_session(db: Session, session_id: int) -> str | None:
    for text in _recent_bot_texts_by_id(db, session_id, limit=10):
        if _has_email_marker(text):
            return text
    return None


def is_email_send_pending(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if _has_email_marker(history_text):
        return True
    if _has_email_marker(_last_assistant_from_history(conversation_history)):
        return True
    if db is not None and chat_session_id is not None:
        return latest_pending_bot_text_from_session(db, chat_session_id) is not None
    return False


def parse_pending_email(text: str | None) -> PendingEmailAction | None:
    if not text:
        return None
    m = _PENDING_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        to = str(data.get("to") or "").strip()
        subject = str(data.get("subject") or "").strip()
        body = str(data.get("body_text") or "").strip()
        if not to or not body:
            return None
        uid = data.get("user_id")
        token = data.get("attachment_export_token")
        return PendingEmailAction(
            to=to,
            subject=subject or "Message Globex FedEx",
            body_text=body,
            user_id=int(uid) if uid is not None else None,
            attachment_export_token=str(token).strip() if token else None,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def resolve_pending_email_action(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> PendingEmailAction | None:
    pending = parse_pending_email(history_text) or parse_pending_email(
        _last_assistant_from_history(conversation_history)
    )
    if pending:
        return pending
    if db is not None and chat_session_id is not None:
        return parse_pending_email(latest_pending_bot_text_from_session(db, chat_session_id))
    return None


def is_email_confirm_message(message: str) -> bool:
    return bool(_CONFIRM_RE.match((message or "").strip()))


def is_email_cancel_message(message: str) -> bool:
    return bool(_CANCEL_RE.match((message or "").strip()))
