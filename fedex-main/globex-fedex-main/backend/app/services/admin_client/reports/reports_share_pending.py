"""Confirmation chat pour partage rapport — pattern PDF clarify."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.admin_client.reports.reports_types import PendingShareAction
from app.services.message_attachment import unpack_message_text

SHARE_CONFIRM_MARKER_FR = "Répondez par oui ou non pour confirmer le partage"
SHARE_CONFIRM_MARKER_EN = "Reply yes or no to confirm sharing"

_PENDING_RE = re.compile(
    r"\[REPORTS_SHARE_PENDING\s+(\{.*?\})\]",
    re.DOTALL,
)
_CONFIRM_RE = re.compile(r"^(oui|confirme|yes|ok|confirmer)\b", re.I)
_CANCEL_RE = re.compile(r"^(non|annule|annuler|cancel|no)\b", re.I)


def build_share_pending_marker(run_id: int, recipient_emails: list[str]) -> str:
    payload = json.dumps({"run_id": run_id, "recipients": recipient_emails}, ensure_ascii=False)
    return f"\n\n[REPORTS_SHARE_PENDING {payload}]"


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


def _has_share_marker(text: str | None) -> bool:
    blob = text or ""
    return SHARE_CONFIRM_MARKER_FR in blob or SHARE_CONFIRM_MARKER_EN in blob or bool(_PENDING_RE.search(blob))


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
        if _has_share_marker(text):
            return text
    return None


def is_share_pending_in_session(db: Session, session_id: int) -> bool:
    return latest_pending_bot_text_from_session(db, session_id) is not None


def is_share_pending(
    *,
    last_bot_text: str | None = None,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if _has_share_marker(last_bot_text):
        return True
    if _has_share_marker(history_text):
        return True
    if _has_share_marker(_last_assistant_from_history(conversation_history)):
        return True
    if db is not None and chat_session_id is not None:
        return is_share_pending_in_session(db, chat_session_id)
    return False


def parse_pending_share(text: str | None) -> PendingShareAction | None:
    if not text:
        return None
    m = _PENDING_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        run_id = int(data.get("run_id"))
        recipients = [str(e).strip() for e in (data.get("recipients") or []) if str(e).strip()]
        if run_id and recipients:
            return PendingShareAction(run_id=run_id, recipient_emails=recipients)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def is_share_confirm_message(message: str) -> bool:
    return bool(_CONFIRM_RE.match((message or "").strip()))


def is_share_cancel_message(message: str) -> bool:
    return bool(_CANCEL_RE.match((message or "").strip()))
