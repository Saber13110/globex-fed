"""Routeur PDF colis / followup admin — sans modifier client_phase3."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.chat_export_service import session_tracking_numbers
from app.services.chat_session_context import (
    build_conversation_history_for_llm,
    resolve_tracking_for_message,
)
from app.services.admin_client.pdf_free_text import extract_literal_pdf_body
from app.services.client_phase3.pdf_postprocess import (
    handle_pdf_only_followup_turn,
    is_pdf_only_followup,
    wants_pdf_format,
)
from app.services.client_phase3.pdf_text import last_bot_message_text
from app.services.client_phase3.pdf_tracking import run_tracking_pdf_export
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number

_SHIPMENT_PDF_REF = re.compile(
    r"\b("
    r"ces\s+infos?|cette\s+r[eé]ponse|ta\s+r[eé]ponse|ton\s+r[eé]ponse|"
    r"ce\s+colis|ce\s+suivi|derni[eè]re\s+r[eé]ponse|"
    r"sous\s+forme|donne\s+(moi\s+)?(ces|ça)"
    r")\b",
    re.I,
)


def is_admin_shipment_pdf_request(
    message: str,
    *,
    has_session_tracking: bool = False,
) -> bool:
    """PDF relatif au colis / dernière réponse — pas texte libre literal."""
    text = (message or "").strip()
    if not wants_pdf_format(text):
        return False
    if extract_literal_pdf_body(text):
        return False
    if is_pdf_only_followup(text):
        return True
    if _SHIPMENT_PDF_REF.search(text):
        return True
    return False


def _clarify_pdf_reply(ui_language: str | None, user: User) -> str:
    lang = (ui_language or user.preferred_language or "fr").lower()[:2]
    if lang == "en":
        return (
            "I don't have shipment data to export yet. "
            "Track a package first, then ask for the PDF again."
        )
    return (
        "Je n'ai pas encore de données colis à exporter. "
        "Consultez d'abord un numéro de suivi, puis redemandez le PDF."
    )


def try_admin_shipment_pdf_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """PDF colis FedEx (direct) ou followup dernière réponse bot."""
    session_tns = session_tracking_numbers(db, session.id, admin.id)
    has_session = bool(session_tns)
    if not is_admin_shipment_pdf_request(message, has_session_tracking=has_session):
        return None

    history = build_conversation_history_for_llm(
        db, session_id=session.id, exclude_message_id=user_msg_id, limit=6
    )
    tracking_number, _src = resolve_tracking_for_message(
        db,
        session_id=session.id,
        user_id=admin.id,
        message=message,
        conversation_history=history,
    )
    tn = extract_tracking_number(message or "")
    if tn and not is_plausible_tracking_number(tn):
        tn = None
    if not tn:
        tn = tracking_number
    if not tn and session_tns:
        tn = session_tns[0]

    if tn and is_plausible_tracking_number(tn):
        tech_reply, export_dl, tn_used = run_tracking_pdf_export(
            db, admin, session, message, ui_language=ui_language
        )
        if export_dl:
            lang = (ui_language or admin.preferred_language or "fr").lower()[:2]
            from app.services.client_phase3.pdf_body_composer import short_pdf_chat_reply

            title = f"Suivi colis {tn_used or tn}"
            reply = short_pdf_chat_reply(lang, doc_title=title)
            return {
                "reply": reply,
                "source": "export",
                "intent": "export_pdf",
                "tracking_number": tn_used or tn,
                "llm_provider": None,
                "shipment": None,
                "export_download": export_dl,
            }
        if tech_reply and "Aucun" not in tech_reply and "Impossible" not in tech_reply:
            pass

    followup = handle_pdf_only_followup_turn(
        db, admin, session, message, ui_language
    )
    if followup is not None:
        return followup

    last_bot = last_bot_message_text(db, session.id)
    if last_bot:
        followup = handle_pdf_only_followup_turn(
            db, admin, session, "mets en pdf", ui_language
        )
        if followup is not None:
            return followup

    return {
        "reply": _clarify_pdf_reply(ui_language, admin),
        "source": "admin_client",
        "intent": "export_pdf_clarify",
        "tracking_number": tn,
        "llm_provider": None,
        "shipment": None,
        "export_download": None,
    }
