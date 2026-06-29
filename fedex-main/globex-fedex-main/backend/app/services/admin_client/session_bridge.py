"""Session miroir pour le pipeline admin_client.

Les modules client réutilisés (`client_phase*`, `_compute_phase2_reply`) exigent une
`ChatSession` persistée avec ses `ChatMessage` (résolution du numéro de suivi en
relance, export PDF de conversation, contexte documents). On crée donc une session
client réelle attachée à l'admin (qui est un `User`) et on y persiste les messages.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.message_attachment import pack_message_text

_DEFAULT_TITLE = "Assistant admin"


def get_or_create_chat_session(
    db: Session,
    admin: User,
    *,
    chat_session_id: int | None = None,
    title_hint: str | None = None,
) -> ChatSession:
    """Récupère la session miroir liée à l'admin ou en crée une nouvelle."""
    if chat_session_id is not None:
        session = db.scalar(
            select(ChatSession).where(
                ChatSession.id == chat_session_id,
                ChatSession.user_id == admin.id,
            )
        )
        if session is not None:
            return session

    title = (title_hint or "").strip() or _DEFAULT_TITLE
    session = ChatSession(user_id=admin.id, title=title[:255])
    db.add(session)
    db.flush()
    return session


def persist_user_message(
    db: Session,
    session: ChatSession,
    message: str,
    *,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    file_name: str | None = None,
) -> ChatMessage:
    """Persiste le message utilisateur (avec pièce jointe encodée) et renvoie l'entité flushée."""
    stored = pack_message_text(
        message,
        image_base64=image_base64,
        image_mime_type=image_mime_type,
        file_name=file_name,
    )
    user_msg = ChatMessage(
        session_id=session.id,
        sender=MessageSender.user.value,
        source="admin_input",
        message_text=stored,
    )
    db.add(user_msg)
    db.flush()
    return user_msg


def persist_bot_message(
    db: Session,
    session: ChatSession,
    reply: str,
    *,
    source: str = "admin_client",
) -> ChatMessage:
    """Persiste la réponse du bot dans la session miroir."""
    bot = ChatMessage(
        session_id=session.id,
        sender=MessageSender.bot.value,
        source=source or "admin_client",
        message_text=reply,
    )
    db.add(bot)
    session.updated_at = func.now()
    db.flush()
    return bot


def _normalize_history_items(
    conversation_history: Sequence[Any] | None,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for raw in conversation_history or []:
        if isinstance(raw, dict):
            role = str(raw.get("role") or "").strip().lower()
            content = str(raw.get("content") or "").strip()
        else:
            role = str(getattr(raw, "role", "") or "").strip().lower()
            content = str(getattr(raw, "content", "") or "").strip()
        if not content:
            continue
        sender = MessageSender.bot.value if role in ("assistant", "bot") else MessageSender.user.value
        items.append((sender, content))
    return items


def sync_history_from_request(
    db: Session,
    session: ChatSession,
    conversation_history: Sequence[Any] | None,
) -> None:
    """Rejoue l'historique frontend dans la session miroir si elle est vide (one-shot).

    Indispensable pour qu'une relance (« en pdf », « montre la carte ») retrouve le
    numéro de suivi évoqué dans les tours précédents lorsque la session vient d'être créée.
    """
    items = _normalize_history_items(conversation_history)
    if not items:
        return

    existing = db.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.session_id == session.id)
    )
    if existing:
        return

    for sender, content in items:
        db.add(
            ChatMessage(
                session_id=session.id,
                sender=sender,
                source="admin_history",
                message_text=content,
            )
        )
    db.flush()


def history_pairs(conversation_history: Iterable[Any] | None) -> list[tuple[str, str]]:
    """Expose la normalisation (rôle, contenu) pour le pipeline."""
    return _normalize_history_items(list(conversation_history or []))
