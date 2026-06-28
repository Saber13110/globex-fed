"""Enrichissement corps ticket — contexte session et FedEx."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.chat_session_context import (
    build_conversation_history_for_llm,
    resolve_tracking_for_message,
)
from app.services.llm.tracking_extract import extract_tracking_number
from app.services.support_ticket_service import sanitize_support_text
from app.utils.tracking_parser import is_plausible_tracking_number

logger = logging.getLogger(__name__)


def enrich_ticket_body(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    message: str,
    body: str,
    tracking_number: str | None,
    exclude_message_id: int | None,
) -> tuple[str, str | None]:
    tn = (tracking_number or "").strip() or extract_tracking_number(message or "")
    if not tn:
        tn = (resolve_tracking_for_message(db, session_id=session.id, message=message) or "").strip()
    if tn and not is_plausible_tracking_number(tn):
        tn = ""

    parts = [sanitize_support_text(body)]
    if tn and tn not in parts[0]:
        parts.append(f"Numéro de suivi : {tn}")

    if tn:
        try:
            from app.services import fedex_service

            data = fedex_service.get_shipment(tn)
            status = data.get("status") or ""
            location = data.get("current_location") or ""
            if status or location:
                parts.append(f"Statut actuel : {status} — {location}".strip(" —"))
        except Exception:
            logger.debug("FedEx enrichment skipped for %s", tn, exc_info=True)

    history = build_conversation_history_for_llm(
        db,
        session_id=session.id,
        exclude_message_id=exclude_message_id,
        limit=4,
    )
    if history:
        snippet = history.replace("\n", " ").strip()[:300]
        if snippet:
            parts.append(f"Contexte chat : {snippet}")

    return "\n".join(p for p in parts if p), (tn or None)
