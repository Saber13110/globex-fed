"""Confirmation chat actions missions agent sensibles."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.admin_client.missions.missions_types import PendingMissionAction
from app.services.message_attachment import unpack_message_text

MISSIONS_CONFIRM_MARKER_FR = "Répondez par oui ou non pour confirmer cette action mission"
MISSIONS_CONFIRM_MARKER_EN = "Reply yes or no to confirm this mission action"
MISSIONS_DELETE_MARKER_FR = "Tapez la phrase exacte pour confirmer la suppression"

_PENDING_RE = re.compile(
    r"\[MISSION_ACTION_PENDING\s+(\{.*?\})\]",
    re.DOTALL,
)
_CONFIRM_RE = re.compile(r"^(oui|confirme|yes|ok|confirmer)\b", re.I)
_CANCEL_RE = re.compile(r"^(non|annule|annuler|cancel|no)\b", re.I)


def build_missions_pending_marker(
    action: str,
    mission_id: int,
    *,
    stage: str = "confirm",
    expected_phrase: str = "",
    payload: dict[str, str] | None = None,
) -> str:
    data = {
        "action": action,
        "mission_id": mission_id,
        "stage": stage,
        "expected_phrase": expected_phrase,
        "payload": payload or {},
    }
    blob = json.dumps(data, ensure_ascii=False)
    return f"\n\n[MISSION_ACTION_PENDING {blob}]"


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


def _has_missions_marker(text: str | None) -> bool:
    blob = text or ""
    return (
        MISSIONS_CONFIRM_MARKER_FR in blob
        or MISSIONS_CONFIRM_MARKER_EN in blob
        or MISSIONS_DELETE_MARKER_FR in blob
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
        if _has_missions_marker(text):
            return text
    return None


def is_missions_action_pending_in_session(db: Session, session_id: int) -> bool:
    return latest_pending_bot_text_from_session(db, session_id) is not None


def is_missions_action_pending(
    *,
    last_bot_text: str | None = None,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> bool:
    if _has_missions_marker(last_bot_text):
        return True
    if _has_missions_marker(history_text):
        return True
    if _has_missions_marker(_last_assistant_from_history(conversation_history)):
        return True
    if db is not None and chat_session_id:
        return is_missions_action_pending_in_session(db, chat_session_id)
    return False


def resolve_pending_mission_action(
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    db: Session | None = None,
    chat_session_id: int | None = None,
) -> PendingMissionAction | None:
    pending = parse_pending_mission_action(history_text) or parse_pending_mission_action(
        _last_assistant_from_history(conversation_history)
    )
    if pending:
        return pending
    if db is not None and chat_session_id:
        return parse_pending_mission_action(latest_pending_bot_text_from_session(db, chat_session_id))
    return None


def parse_pending_mission_action(text: str | None) -> PendingMissionAction | None:
    if not text:
        return None
    m = _PENDING_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        action = str(data.get("action") or "").strip()
        mission_id = int(data.get("mission_id"))
        stage = str(data.get("stage") or "confirm")
        expected_phrase = str(data.get("expected_phrase") or "")
        payload = data.get("payload") or {}
        if action and mission_id:
            return PendingMissionAction(
                action=action,
                mission_id=mission_id,
                stage=stage,
                expected_phrase=expected_phrase,
                payload={str(k): str(v) for k, v in payload.items()},
            )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def is_missions_confirm_message(message: str) -> bool:
    return bool(_CONFIRM_RE.match((message or "").strip()))


def is_missions_cancel_message(message: str) -> bool:
    return bool(_CANCEL_RE.match((message or "").strip()))


def is_missions_delete_phrase(message: str, expected_phrase: str) -> bool:
    user = (message or "").strip()
    expected = (expected_phrase or "").strip()
    if not user or not expected:
        return False
    return user.casefold() == expected.casefold()
