"""Confirmation chat actions utilisateurs sensibles."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.admin_client.users.users_types import PendingUserAction
from app.services.message_attachment import unpack_message_text

USERS_CONFIRM_MARKER_FR = "Répondez par oui ou non pour confirmer cette action"
USERS_CONFIRM_MARKER_EN = "Reply yes or no to confirm this action"

_PENDING_RE = re.compile(
    r"\[USERS_ACTION_PENDING\s+(\{.*?\})\]",
    re.DOTALL,
)
_CONFIRM_RE = re.compile(r"^(oui|confirme|yes|ok|confirmer)\b", re.I)
_CANCEL_RE = re.compile(r"^(non|annule|annuler|cancel|no)\b", re.I)


def build_users_pending_marker(action: str, user_id: int, payload: dict[str, str] | None = None) -> str:
    data = {"action": action, "user_id": user_id, "payload": payload or {}}
    blob = json.dumps(data, ensure_ascii=False)
    return f"\n\n[USERS_ACTION_PENDING {blob}]"


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


def _has_users_marker(text: str | None) -> bool:
    blob = text or ""
    return (
        USERS_CONFIRM_MARKER_FR in blob
        or USERS_CONFIRM_MARKER_EN in blob
        or bool(_PENDING_RE.search(blob))
    )


def _recent_bot_texts_by_id(db: Session, session_id: int, *, limit: int = 5) -> list[str]:
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
    for text in _recent_bot_texts_by_id(db, session_id, limit=8):
        if _has_users_marker(text):
            return text
    return None


def is_users_action_pending_in_session(db: Session, session_id: int) -> bool:
    return latest_pending_bot_text_from_session(db, session_id) is not None


def is_users_action_pending(
    *,
    last_bot_text: str | None = None,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if _has_users_marker(last_bot_text):
        return True
    if _has_users_marker(history_text):
        return True
    if _has_users_marker(_last_assistant_from_history(conversation_history)):
        return True
    if db is not None and chat_session_id:
        return is_users_action_pending_in_session(db, chat_session_id)
    return False


def resolve_pending_user_action(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> PendingUserAction | None:
    pending = parse_pending_user_action(history_text) or parse_pending_user_action(
        _last_assistant_from_history(conversation_history)
    )
    if pending:
        return pending
    if db is not None and chat_session_id:
        return parse_pending_user_action(latest_pending_bot_text_from_session(db, chat_session_id))
    return None


def parse_pending_user_action(text: str | None) -> PendingUserAction | None:
    if not text:
        return None
    m = _PENDING_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        action = str(data.get("action") or "").strip()
        user_id = int(data.get("user_id"))
        payload = data.get("payload") or {}
        if action and user_id:
            return PendingUserAction(
                action=action,
                user_id=user_id,
                payload={str(k): str(v) for k, v in payload.items()},
            )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def is_users_confirm_message(message: str) -> bool:
    return bool(_CONFIRM_RE.match((message or "").strip()))


def is_users_cancel_message(message: str) -> bool:
    return bool(_CANCEL_RE.match((message or "").strip()))
