"""Follow-up « envoie-le par mail » — Phase 7."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.ai_assistant.export_dataset_cache import get_owner_export_dataset
from app.services.client_phase7.capabilities import has_email_export_capability, router_enabled
from app.services.client_phase7.export_email_hook import (
    append_export_email_suffix,
    extract_file_bytes_from_cache,
    finalize_export_delivery,
)
from app.services.client_phase7.export_email_intent import is_export_email_only_followup
from app.services.client_phase7.export_email_service import build_email_suffix
from app.services.client_phase7.export_session_pointer import get_session_export_pointer
from app.services.email_service import is_email_configured

logger = logging.getLogger(__name__)


def _lang(user: User, ui_language: str | None) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def _turn_result(reply: str, export_download: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "reply": reply,
        "source": "export_email",
        "intent": "export_email_delivery",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": export_download,
    }


def _send_from_cache(
    user: User,
    session: ChatSession,
    message: str,
    cached: dict[str, Any],
    fmt: str,
    filename: str,
    ui_language: str | None,
) -> dict[str, Any] | None:
    file_bytes = extract_file_bytes_from_cache(cached, fmt)
    if not file_bytes:
        return None
    token = cached.get("export_token") or cached.get("token")
    spec = {
        "export_token": token,
        "filename": filename,
        "format": fmt,
        "session_id": session.id,
        "preset": cached.get("module") or cached.get("source") or "export",
    }
    lang = _lang(user, ui_language)
    doc_label = "Export FedEx Globex" if lang != "en" else "FedEx Globex export"
    reply_base = (
        "I resent the file from your last export."
        if lang == "en"
        else "Je vous ai renvoyé le fichier de votre dernier export."
    )
    reply, spec = finalize_export_delivery(
        user,
        session.id,
        message,
        reply_base,
        spec,
        file_bytes,
        filename,
        fmt,
        doc_label,
        ui_language=ui_language,
    )
    return _turn_result(reply, spec)


def try_export_email_only_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """
    Envoie par mail le dernier export de la session (cache) ou regénère via Phase 3.
    """
    if not router_enabled() or not has_email_export_capability():
        return None
    if not is_export_email_only_followup(message):
        return None

    lang = _lang(user, ui_language)
    ptr = get_session_export_pointer(session.id)
    if ptr is not None:
        cached = get_owner_export_dataset(ptr.export_token, owner_id=user.id)
        if cached:
            turn = _send_from_cache(
                user,
                session,
                message,
                cached,
                ptr.fmt,
                ptr.filename,
                ui_language,
            )
            if turn is not None:
                return turn

    from app.services.client_phase3.excel_postprocess import handle_excel_only_followup_turn
    from app.services.client_phase3.pdf_postprocess import (
        handle_conversation_pdf_turn,
        handle_pdf_only_followup_turn,
    )
    from app.services.client_phase7.export_email_intent import normalize_message_text

    text = normalize_message_text(message)
    regen = None
    if "excel" in text or "xlsx" in text:
        regen = handle_excel_only_followup_turn(db, user, session, message, ui_language)
    elif any(k in text for k in ("conversation", "discussion", "resume", "résumé")):
        regen = handle_conversation_pdf_turn(
            db, user, session, message, 0, ui_language
        )
    else:
        regen = (
            handle_pdf_only_followup_turn(db, user, session, message, ui_language)
            or handle_excel_only_followup_turn(db, user, session, message, ui_language)
        )

    if regen and regen.get("export_download"):
        return regen

    has_email = bool((user.email or "").strip())
    smtp_ok = is_email_configured()
    if lang == "en":
        clarify = (
            "Which document should I email? Generate a PDF or Excel export first, "
            "or specify what you need (shipment PDF, conversation, notifications…)."
        )
    else:
        clarify = (
            "Quel document souhaitez-vous recevoir par mail ? "
            "Générez d'abord un export PDF ou Excel, ou précisez le document voulu."
        )
    suffix = build_email_suffix(
        user,
        sent=False,
        smtp_ok=smtp_ok,
        has_email=has_email,
        lang=lang,
    )
    return _turn_result(append_export_email_suffix(clarify, suffix))
