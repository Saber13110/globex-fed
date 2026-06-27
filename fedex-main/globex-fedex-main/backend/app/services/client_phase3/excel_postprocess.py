"""Phase 3d — Excel post-réponse : chat court + fichier enrichi séparé."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.client_phase3.capabilities import CAP_EXCEL, has_capability
from app.services.client_phase3.excel_body_composer import (
    build_excel_body_for_shipment_turn,
    short_excel_chat_reply,
)
from app.services.client_phase3.excel_download import build_excel_download
from app.services.client_phase3.export_intent import is_excel_export_intent
from app.services.client_phase3.export_router import _capability_disabled_reply
from app.services.client_phase3.pdf_postprocess import (
    clarify_pdf_followup,
    wants_pdf_format,
)
from app.services.client_phase3.pdf_text import last_bot_message_text
from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

_EXCEL_FORMAT = re.compile(r"\b(excel|xlsx|tableur)\b", re.I)
_EXCEL_FOLLOWUP_REF = re.compile(
    r"\b("
    r"ces\s+infos?|cette\s+r[eé]ponse|ta\s+r[eé]ponse|ton\s+r[eé]ponse|"
    r"ce\s+que\s+tu\s+(viens\s+de\s+)?(dire|dit)|derni[eè]re\s+r[eé]ponse|"
    r"mets?\s+[çc]a|met\s+[çc]a|sous\s+forme|donne\s+(moi\s+)?(ces|ça)|"
    r"en\s+excel|au\s+format\s+(excel|xlsx)"
    r")\b",
    re.I,
)
_TRACKING_IN_MSG = re.compile(
    r"\b(colis|suivi|tracking|livraison|exp[eé]dition|shipments?)\b",
    re.I,
)


def wants_excel_format(message: str) -> bool:
    return is_excel_export_intent(message)


def is_excel_only_followup(message: str) -> bool:
    """Demande Excel sans nouvelle question (ex. « ces infos en excel »)."""
    text = (message or "").strip()
    if not wants_excel_format(text):
        return False
    if wants_pdf_format(text):
        return False
    if extract_tracking_number(text):
        return False
    if _TRACKING_IN_MSG.search(text) and len(text) > 40:
        return False
    if _EXCEL_FOLLOWUP_REF.search(text):
        return True
    if len(text) <= 80 and _EXCEL_FORMAT.search(text):
        return True
    return False


def _lang_code(ui_language: str | None, user: User) -> str:
    return (ui_language or user.preferred_language or "fr").lower()[:2]


def _excel_error_turn(
    ui_language: str | None,
    user: User,
    exc: ValueError | None = None,
) -> dict[str, Any]:
    lang = _lang_code(ui_language, user)
    reply = (
        str(exc).strip()
        if exc and str(exc).strip()
        else (
            "Unable to generate the Excel file. Please try again or rephrase your request."
            if lang == "en"
            else "Impossible de générer le fichier Excel. Réessayez ou reformulez votre demande."
        )
    )
    return {
        "reply": reply,
        "source": "phase3",
        "intent": "export_excel_error",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": None,
    }


def _build_excel_turn_result(
    user: User,
    session: ChatSession,
    xlsx_bytes: bytes,
    filename: str,
    *,
    tracking_number: str | None,
    ui_language: str | None,
    llm_provider: str | None = "ollama",
) -> dict[str, Any]:
    lang = _lang_code(ui_language, user)
    doc_title = f"Suivi colis {tracking_number}" if tracking_number else filename
    export_download = build_excel_download(
        user.id,
        xlsx_bytes,
        filename=filename,
        session_id=session.id,
    )
    return {
        "reply": short_excel_chat_reply(lang, doc_title=doc_title),
        "source": "export",
        "intent": "export_excel",
        "tracking_number": tracking_number,
        "llm_provider": llm_provider,
        "shipment": None,
        "export_download": export_download,
    }


def handle_excel_only_followup_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Traite les demandes Excel pures (sans nouvelle question) avant Phase 2."""
    if not is_excel_only_followup(message):
        return None
    if not has_capability(CAP_EXCEL):
        return {
            "reply": _capability_disabled_reply(ui_language, user, "export Excel"),
            "source": "phase3",
            "intent": "export_excel_disabled",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
        }

    clarification = clarify_pdf_followup(db, session, user, message, ui_language)
    if clarification:
        lang = _lang_code(ui_language, user)
        if lang == "en":
            clarification = clarification.replace("PDF", "Excel file").replace("pdf", "Excel")
        else:
            clarification = clarification.replace("PDF", "fichier Excel").replace("pdf", "Excel")
        return {
            "reply": clarification,
            "source": "phase3",
            "intent": "export_excel_clarify",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
        }

    last_bot = last_bot_message_text(db, session.id)
    if not last_bot:
        return None

    lang = _lang_code(ui_language, user)
    xlsx_bytes, filename, tn_used = build_excel_body_for_shipment_turn(
        message,
        last_bot_text=last_bot,
        chat_context=None,
        tracking_number=None,
        lang=lang,
    )
    if not xlsx_bytes:
        return _excel_error_turn(ui_language, user)

    try:
        return _build_excel_turn_result(
            user,
            session,
            xlsx_bytes,
            filename,
            tracking_number=tn_used or extract_tracking_number(last_bot),
            ui_language=ui_language,
        )
    except ValueError as exc:
        return _excel_error_turn(ui_language, user, exc)


def maybe_attach_excel_export(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
    *,
    chat_reply: str,
    tracking_number: str | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """
    Après Phase 2 : génère Excel enrichi si demandé.
    Retourne (reply_finale, export_download, intent_override).
    """
    _ = user_msg_id
    if not wants_excel_format(message) or wants_pdf_format(message):
        return chat_reply, None, None

    if not has_capability(CAP_EXCEL):
        disabled = _capability_disabled_reply(ui_language, user, "export Excel")
        return disabled, None, "export_excel_disabled"

    lang = _lang_code(ui_language, user)
    last_bot = last_bot_message_text(db, session.id)
    xlsx_bytes, filename, tn_used = build_excel_body_for_shipment_turn(
        message,
        last_bot_text=last_bot,
        chat_context=chat_reply,
        tracking_number=tracking_number,
        lang=lang,
    )
    if not xlsx_bytes:
        clarification = clarify_pdf_followup(db, session, user, message, ui_language)
        if clarification:
            if lang == "en":
                clarification = clarification.replace("PDF", "Excel file")
            else:
                clarification = clarification.replace("PDF", "fichier Excel")
            return clarification, None, "export_excel_clarify"
        err = (
            "I could not prepare the Excel file. Please rephrase your request."
            if lang == "en"
            else "Je n'ai pas pu préparer le fichier Excel. Reformulez votre demande."
        )
        return err, None, "export_excel_error"

    try:
        export_download = build_excel_download(
            user.id,
            xlsx_bytes,
            filename=filename,
            session_id=session.id,
        )
    except ValueError:
        err = (
            "Unable to generate the Excel file. Please try again."
            if lang == "en"
            else "Impossible de générer le fichier Excel. Réessayez."
        )
        return err, None, "export_excel_error"

    doc_title = f"Suivi colis {tn_used or tracking_number}" if (tn_used or tracking_number) else filename
    return short_excel_chat_reply(lang, doc_title=doc_title), export_download, "export_excel"
