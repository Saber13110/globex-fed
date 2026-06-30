"""Résolution du marqueur pending le plus récent — évite les collisions inter-agents."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.message_attachment import unpack_message_text

PendingKind = Literal[
    "email_send",
    "email_offer",
    "share",
    "users",
    "tickets",
    "logs",
    "missions",
]


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


def _recent_bot_texts_by_id(db: Session, session_id: int, *, limit: int = 12) -> list[str]:
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


def detect_pending_kind_in_text(text: str | None) -> PendingKind | None:
    """Type de pending dans un message bot (un seul marqueur attendu par message)."""
    if not text:
        return None

    from app.services.admin_client.email.email_pending import _has_email_marker
    from app.services.admin_client.email.email_action_offer import _has_offer_marker
    from app.services.admin_client.reports.reports_share_pending import _has_share_marker
    from app.services.admin_client.users.users_pending import _has_users_marker
    from app.services.admin_client.tickets.tickets_pending import _has_tickets_marker
    from app.services.admin_client.logs.logs_pending import _has_marker as _has_logs_marker
    from app.services.admin_client.missions.missions_pending import _has_missions_marker

    if _has_email_marker(text):
        return "email_send"
    if _has_offer_marker(text):
        return "email_offer"
    if _has_share_marker(text):
        return "share"
    if _has_users_marker(text):
        return "users"
    if _has_tickets_marker(text):
        return "tickets"
    if _has_logs_marker(text):
        return "logs"
    if _has_missions_marker(text):
        return "missions"
    return None


def iter_bot_texts_newest_first(
    *,
    db: Session | None = None,
    chat_session_id: int | None = None,
    conversation_history: list[Any] | None = None,
) -> list[str]:
    """Messages bot du plus récent au plus ancien (session DB puis fil LLM)."""
    ordered: list[str] = []
    seen: set[str] = set()

    if db is not None and chat_session_id is not None:
        for text in _recent_bot_texts_by_id(db, chat_session_id):
            if text not in seen:
                ordered.append(text)
                seen.add(text)

    last = _last_assistant_from_history(conversation_history)
    if last and last not in seen:
        ordered.insert(0, last)

    return ordered


def resolve_latest_pending_kind(
    *,
    db: Session | None = None,
    chat_session_id: int | None = None,
    conversation_history: list[Any] | None = None,
) -> PendingKind | None:
    """
    Retourne le type de pending du message bot le plus récent qui en contient un.
    Ignore les marqueurs obsolètes plus anciens dans la même session.
    """
    for text in iter_bot_texts_newest_first(
        db=db,
        chat_session_id=chat_session_id,
        conversation_history=conversation_history,
    ):
        kind = detect_pending_kind_in_text(text)
        if kind:
            return kind
    return None


def is_latest_pending_kind(
    kind: PendingKind,
    *,
    db: Session | None = None,
    chat_session_id: int | None = None,
    conversation_history: list[Any] | None = None,
) -> bool:
    return resolve_latest_pending_kind(
        db=db,
        chat_session_id=chat_session_id,
        conversation_history=conversation_history,
    ) == kind
