"""Suite admin du dialogue PDF « Répondez par 1 ou 2 » — sans modifier client_phase3."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.user import User
from app.services.admin_client.capabilities import has_admin_capability
from app.services.client_phase3.capabilities import CAP_PDF, has_capability
from app.services.client_phase3.export_router import _capability_disabled_reply
from app.services.client_phase3.pdf_body_composer import (
    build_pdf_body_for_shipment_turn,
    short_pdf_chat_reply,
    strip_markdown_for_pdf,
)
from app.services.client_phase3.pdf_postprocess import handle_conversation_pdf_turn
from app.services.client_phase3.pdf_text import (
    append_pdf_ready_note,
    build_text_pdf_download,
)
from app.services.llm.tracking_extract import extract_tracking_number
from app.services.message_attachment import unpack_message_text

_CLARIFY_MARKER_FR = "Répondez par 1 ou 2"
_CLARIFY_MARKER_EN = "Reply with option 1 or 2"
_CHOICE = re.compile(r"^(?:option\s*)?[12]\.?\s*$", re.I)


def _lang_code(ui_language: str | None, user: User) -> str:
    return (ui_language or user.preferred_language or "fr").lower()[:2]


def _has_clarify_marker(text: str | None) -> bool:
    blob = (text or "").strip()
    if not blob:
        return False
    return _CLARIFY_MARKER_FR in blob or _CLARIFY_MARKER_EN in blob


def is_pdf_clarify_choice_message(message: str) -> bool:
    return bool(_CHOICE.match((message or "").strip()))


def parse_pdf_clarify_choice(message: str) -> int | None:
    text = (message or "").strip()
    match = _CHOICE.match(text)
    if not match:
        return None
    digit = text[0] if text[0] in "12" else text[-1]
    return int(digit) if digit in "12" else None


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


def is_pdf_clarify_pending(
    *,
    last_bot_text: str | None = None,
    conversation_history: list[Any] | None = None,
) -> bool:
    """Vrai si le bot attend un choix 1/2 après clarification PDF."""
    if _has_clarify_marker(last_bot_text):
        return True
    return _has_clarify_marker(_last_assistant_from_history(conversation_history))


def is_pdf_clarify_pending_from_history(conversation_history: list[Any] | None) -> bool:
    return is_pdf_clarify_pending(conversation_history=conversation_history)


def _recent_bot_texts_by_id(db: Session, session_id: int, *, limit: int = 5) -> list[str]:
    """Messages bot récents ordonnés par id (fiable si created_at identique en tests)."""
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


def _latest_clarify_bot_text(recent_bots: list[str]) -> str | None:
    for text in recent_bots:
        if _has_clarify_marker(text):
            return text
    return None


def _find_shipment_bot_text(recent_bot_texts: list[str]) -> str | None:
    for text in recent_bot_texts:
        if _has_clarify_marker(text):
            continue
        if extract_tracking_number(text or ""):
            return text
    return None


def is_pdf_clarify_pending_in_session(db: Session, session_id: int) -> bool:
    recent = _recent_bot_texts_by_id(db, session_id, limit=5)
    return _latest_clarify_bot_text(recent) is not None


def _pdf_disabled_turn(admin: User, ui_language: str | None) -> dict[str, Any]:
    return {
        "reply": _capability_disabled_reply(ui_language, admin, "export PDF"),
        "source": "admin_client",
        "intent": "export_pdf_disabled",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": None,
    }


def _no_shipment_reply(admin: User, ui_language: str | None) -> dict[str, Any]:
    lang = _lang_code(ui_language, admin)
    reply = (
        "I couldn't find a recent shipment reply to export. "
        "Track a package first, then ask for the PDF again."
        if lang == "en"
        else (
            "Je n'ai pas trouvé de réponse colis récente à exporter. "
            "Consultez d'abord un suivi, puis redemandez le PDF."
        )
    )
    return {
        "reply": reply,
        "source": "admin_client",
        "intent": "export_pdf_clarify",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": None,
    }


def _export_shipment_bot_pdf(
    admin: User,
    session,
    message: str,
    shipment_bot: str,
    ui_language: str | None,
) -> dict[str, Any]:
    lang = _lang_code(ui_language, admin)
    pdf_body, tn_used = build_pdf_body_for_shipment_turn(
        message,
        last_bot_text=shipment_bot,
        chat_context=None,
        tracking_number=None,
        lang=lang,
    )
    if not pdf_body:
        pdf_body = strip_markdown_for_pdf(shipment_bot)

    title = f"Suivi colis {tn_used}" if tn_used else "Réponse assistant FedEx"
    try:
        export_download = build_text_pdf_download(
            admin.id,
            pdf_body,
            title=title,
            session_id=session.id,
        )
    except ValueError as exc:
        return {
            "reply": str(exc),
            "source": "admin_client",
            "intent": "export_pdf_error",
            "tracking_number": tn_used,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
        }

    reply = append_pdf_ready_note(short_pdf_chat_reply(lang, doc_title=title))
    return {
        "reply": reply,
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": tn_used or extract_tracking_number(shipment_bot),
        "llm_provider": None,
        "shipment": None,
        "export_download": export_download,
    }


def _conversation_summary_message(ui_language: str | None, admin: User) -> str:
    lang = _lang_code(ui_language, admin)
    if lang == "en":
        return "make a summary of our conversation in pdf"
    return "fais un résumé de notre conversation en pdf"


def try_admin_pdf_clarify_choice_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Interprète « 1 » / « 2 » après clarification PDF multi-colis."""
    choice = parse_pdf_clarify_choice(message)
    if choice is None:
        return None

    recent = _recent_bot_texts_by_id(db, session.id, limit=5)
    if _latest_clarify_bot_text(recent) is None:
        return None

    if not has_admin_capability(CAP_PDF) and not has_capability(CAP_PDF):
        return _pdf_disabled_turn(admin, ui_language)

    if choice == 2:
        return handle_conversation_pdf_turn(
            db,
            admin,
            session,
            _conversation_summary_message(ui_language, admin),
            user_msg_id,
            ui_language,
        )

    shipment_bot = _find_shipment_bot_text(recent)
    if not shipment_bot:
        return _no_shipment_reply(admin, ui_language)

    return _export_shipment_bot_pdf(
        admin, session, message, shipment_bot, ui_language
    )
