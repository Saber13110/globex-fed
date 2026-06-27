"""Contexte conversationnel : numéro de suivi actif et historique des messages."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.services.chat_export_service import is_export_intent, session_tracking_numbers
from app.services.chat_shipment_reply import is_session_follow_up
from app.services.llm.intent_detection import is_general_logistics_question, is_off_topic_general_question
from app.services.llm.tracking_extract import extract_all_tracking_numbers, extract_tracking_number
from app.services.message_attachment import unpack_message_text

_GREETING_ONLY = re.compile(
    r"^(bonjour|salut|hello|hi|coucou|merci|thanks|thank you|ok merci|de rien|au revoir|bye)\b",
    re.IGNORECASE,
)


def _tracking_from_session_messages(db: Session, session_id: int, *, limit: int = 40) -> str | None:
    """Dernier numéro de suivi mentionné dans la session (le plus récent)."""
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).all()
    )
    for row in rows:
        text, _, _ = unpack_message_text(row.message_text or "")
        nums = extract_all_tracking_numbers(text or "")
        if nums:
            return nums[-1]
    return None


def last_session_tracking(db: Session, *, session_id: int, user_id: int) -> str | None:
    nums = session_tracking_numbers(db, session_id, user_id)
    if nums:
        return nums[-1]
    return _tracking_from_session_messages(db, session_id)


def resolve_tracking_from_history_text(history: str) -> str | None:
    """Extrait le dernier numéro de suivi mentionné dans l'historique conversationnel."""
    if not history:
        return None
    found: list[str] = []
    for line in history.splitlines():
        for tn in extract_all_tracking_numbers(line):
            found.append(tn)
    return found[-1] if found else None


def resolve_tracking_for_message(
    db: Session,
    *,
    session_id: int,
    user_id: int,
    message: str,
    conversation_history: str | None = None,
) -> tuple[str | None, str]:
    """
    Résout le numéro de suivi : message courant, puis contexte session.
    Retourne (numéro, source) avec source « message » | « session » | « none ».
    """
    from_message = extract_tracking_number(message)
    if from_message:
        return from_message, "message"

    last = last_session_tracking(db, session_id=session_id, user_id=user_id)
    if not last and conversation_history:
        last = resolve_tracking_from_history_text(conversation_history)

    if not last:
        return None, "none"

    if message_unrelated_to_shipment(message):
        return None, "none"

    return last, "session"


def message_unrelated_to_shipment(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return True
    if is_off_topic_general_question(text):
        return True
    if is_general_logistics_question(text):
        return True
    if is_export_intent(text):
        return True
    if _GREETING_ONLY.match(lowered) and len(lowered) < 48:
        return True
    if is_session_follow_up(text):
        return False
    package_words = (
        "colis",
        "package",
        "suivi",
        "tracking",
        "livraison",
        "delivery",
        "fedex",
        "pod",
        "carte",
        "map",
        "historique",
        "scan",
        "expédition",
        "expedition",
        "shipment",
        "parcel",
        "arrive",
        "arrivée",
        "arrivee",
        "temps",
        "quand",
        "when",
        "tableau",
        "طرد",
        "شحنة",
    )
    return not any(word in lowered for word in package_words)


def build_conversation_history_for_llm(
    db: Session,
    *,
    session_id: int,
    exclude_message_id: int | None = None,
    limit: int = 14,
) -> str:
    """Historique récent pour le LLM (sans le message utilisateur en cours)."""
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit + (1 if exclude_message_id else 0))
        ).all()
    )
    lines: list[str] = []
    for row in reversed(rows):
        if exclude_message_id and row.id == exclude_message_id:
            continue
        text, _, _ = unpack_message_text(row.message_text or "")
        text = (text or "").strip()
        if not text:
            continue
        if len(text) > 600:
            text = text[:600] + "…"
        role = "Utilisateur" if row.sender == MessageSender.user.value else "Assistant"
        lines.append(f"{role}: {text}")
        if len(lines) >= limit:
            break
    return "\n".join(lines)
