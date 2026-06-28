"""Mémoire document de session — questions de suivi sans re-pièce jointe."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.client_phase9.document_reader import (
    ResolvedAttachment,
    resolve_attachment,
    try_document_read_turn,
)
from app.services.message_attachment import unpack_message_attachment

_LIVE_TRACKING_RE = re.compile(
    r"\b(où est|ou est|where is|statut actuel|localisation|position du colis|en direct)\b",
    re.I,
)

_DOCUMENT_FOLLOWUP_RE = re.compile(
    r"\b("
    r"extrait|extrais|extraire|donne|donne-moi|donnez|quel est|quelle est|"
    r"numéro|numero|n°|contexte|contenu|résume|resume|fichier|document|"
    r"dans ce|du pdf|de ce|de ce fichier|dans le fichier|"
    r"what is|summarize|summary|extract|content of|from the file|in the file|"
    r"identifier|identifie"
    r")\b",
    re.I,
)


def is_document_followup_question(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _LIVE_TRACKING_RE.search(text):
        return False
    return bool(_DOCUMENT_FOLLOWUP_RE.search(text))


def find_recent_session_attachment(
    db: Session,
    session_id: int,
    *,
    exclude_message_id: int | None = None,
    limit: int = 12,
) -> ResolvedAttachment | None:
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.sender == MessageSender.user.value,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(limit + (1 if exclude_message_id else 0))
        ).all()
    )
    for row in rows:
        if exclude_message_id and row.id == exclude_message_id:
            continue
        _, b64, mime, name, _kind = unpack_message_attachment(row.message_text or "")
        if not b64 or not mime:
            continue
        att = resolve_attachment(
            attachment_base64=b64,
            attachment_mime_type=mime,
            file_name=name,
        )
        if att is not None:
            return att
    return None


def try_document_followup_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    user_msg_id: int,
    *,
    ui_language: str | None,
    compute_phase2_reply: Any,
) -> dict[str, Any] | None:
    if not is_document_followup_question(message):
        return None
    attachment = find_recent_session_attachment(
        db,
        session.id,
        exclude_message_id=user_msg_id,
    )
    if attachment is None:
        return None
    return try_document_read_turn(
        db,
        user,
        session,
        message,
        user_msg_id,
        attachment=attachment,
        ui_language=ui_language,
        compute_phase2_reply=compute_phase2_reply,
    )
