"""Confirmation actions sensibles depuis les logs."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.admin_client.logs.logs_types import PendingLogAction
from app.services.message_attachment import unpack_message_text

LOGS_CONFIRM_MARKER_FR = "Répondez par oui ou non pour confirmer cette action sur le log"
LOGS_CONFIRM_MARKER_EN = "Reply yes or no to confirm this log action"

_PENDING_RE = re.compile(
    r"\[LOGS_ACTION_PENDING\s+(\{.*?\})\]",
    re.DOTALL,
)
_CONFIRM_RE = re.compile(r"^(oui|confirme|yes|ok|confirmer)\b", re.I)
_CANCEL_RE = re.compile(r"^(non|annule|annuler|cancel|no)\b", re.I)


def build_logs_pending_marker(
    action: str,
    *,
    log_id: int = 0,
    user_id: int = 0,
    payload: dict[str, str] | None = None,
) -> str:
    data = {
        "action": action,
        "log_id": log_id,
        "user_id": user_id,
        "payload": payload or {},
    }
    blob = json.dumps(data, ensure_ascii=False)
    return f"\n\n[LOGS_ACTION_PENDING {blob}]"


def _has_marker(text: str | None) -> bool:
    blob = text or ""
    return (
        LOGS_CONFIRM_MARKER_FR in blob
        or LOGS_CONFIRM_MARKER_EN in blob
        or bool(_PENDING_RE.search(blob))
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


def latest_pending_bot_text_from_session(db: Session, session_id: int) -> str | None:
    for msg in db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.sender == MessageSender.bot.value,
        )
        .order_by(ChatMessage.id.desc())
        .limit(8)
    ).all():
        text, _, _ = unpack_message_text(msg.message_text or "")
        if _has_marker(text):
            return text
    return None


def is_logs_action_pending_in_session(db: Session, session_id: int) -> bool:
    return latest_pending_bot_text_from_session(db, session_id) is not None


def is_logs_action_pending(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if _has_marker(history_text):
        return True
    if _has_marker(_last_assistant_from_history(conversation_history)):
        return True
    if db is not None and chat_session_id:
        return is_logs_action_pending_in_session(db, chat_session_id)
    return False


def parse_pending_log_action(text: str | None) -> PendingLogAction | None:
    if not text:
        return None
    m = _PENDING_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        action = str(data.get("action") or "").strip()
        log_id = int(data.get("log_id") or 0) or None
        user_id = int(data.get("user_id") or 0) or None
        payload = data.get("payload") or {}
        if action and user_id:
            return PendingLogAction(
                action=action,
                log_id=log_id,
                user_id=user_id,
                payload={str(k): str(v) for k, v in payload.items()},
            )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def resolve_pending_log_action(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> PendingLogAction | None:
    pending = parse_pending_log_action(history_text) or parse_pending_log_action(
        _last_assistant_from_history(conversation_history)
    )
    if pending:
        return pending
    if db is not None and chat_session_id:
        return parse_pending_log_action(latest_pending_bot_text_from_session(db, chat_session_id))
    return None


def is_logs_confirm_message(message: str) -> bool:
    return bool(_CONFIRM_RE.match((message or "").strip()))


def is_logs_cancel_message(message: str) -> bool:
    return bool(_CANCEL_RE.match((message or "").strip()))
