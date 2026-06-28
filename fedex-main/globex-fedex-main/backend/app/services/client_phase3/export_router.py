"""Routeur export client Phase 3a — DISABLED (remplacé par pdf_postprocess).

Conservé pour référence : Excel (_run_excel_export) et messages capability.
Ne pas réactiver handle_client_export_turn dans chatbot_service sans accord explicite.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.chat_export_service import session_tracking_numbers
from app.services.client_phase3.capabilities import CAP_EXCEL, CAP_PDF, has_capability
from app.services.client_phase3.export_intent import (
    PdfKind,
    classify_pdf_kind,
    is_client_export_request,
    is_excel_export_intent,
    is_pdf_export_intent,
)
from app.services.client_phase3.pdf_text import run_text_pdf_export
from app.services.client_phase3.pdf_tracking import run_tracking_pdf_export
from app.services.gpt.orchestrator import SLUG_CLIENT
from app.services.gpt.tool_executor import execute_tool
from app.services.gpt.tool_types import ToolCall, ToolExecutionContext


def _capability_disabled_reply(ui_language: str | None, user: User, feature: str) -> str:
    lang = (ui_language or user.preferred_language or "fr").lower()[:2]
    if lang == "en":
        return f"The **{feature}** feature is not enabled on this server yet."
    return f"La fonctionnalité **{feature}** n'est pas encore activée sur ce serveur."


def _run_excel_export(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    ui_language: str | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    from app.services.llm.tracking_extract import extract_tracking_number

    tn = extract_tracking_number(message or "")
    scope = "session" if session_tracking_numbers(db, session.id, user.id) or tn else "recent"
    args: dict[str, Any] = {"scope": scope, "limit": 20}
    if tn:
        args["tracking_number"] = tn

    lang = (ui_language or user.preferred_language or "fr").lower()[:2]
    ctx = ToolExecutionContext(
        db=db,
        user_id=user.id,
        user_role="client",
        gpt_slug=SLUG_CLIENT,
        ui_language=lang,
        skip_approval=True,
        session_id=session.id,
    )
    result = execute_tool(ctx, ToolCall(name="client_export_tracking_excel", args=args))
    if not result.success:
        return result.error or "Export Excel impossible.", None, tn

    export_dl = result.data.get("export_download")
    if not export_dl:
        return "L'export Excel n'a pas pu être préparé.", None, tn

    tns = export_dl.get("tracking_numbers") or []
    tracking_number = tns[0] if len(tns) == 1 else (tn or (tns[0] if tns else None))
    count = len(tns)
    label = tracking_number if count <= 1 else f"{count} colis"
    reply = (
        f"Votre export Excel pour **{label}** est prêt.\n\n"
        "Le fichier contient les données de suivi (statut, localisation, ETA).\n\n"
        "Utilisez le lien de téléchargement ci-dessous."
    )
    export_dl.setdefault("format", "xlsx")
    return reply, export_dl, tracking_number


def handle_client_export_turn(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """
    DISABLED Phase 3a — remplacé par pdf_postprocess (LLM d'abord, PDF ensuite).
    Retourne toujours None ; corps legacy commenté ci-dessous pour référence.
    """
    return None

    # --- Legacy Phase 3a (ne pas réactiver) ---
    if not is_client_export_request(message):
        return None

    wants_pdf = is_pdf_export_intent(message)
    wants_excel = is_excel_export_intent(message) and not wants_pdf

    if wants_pdf and not has_capability(CAP_PDF):
        return {
            "reply": _capability_disabled_reply(ui_language, user, "export PDF"),
            "source": "phase3",
            "intent": "export_pdf_disabled",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
            "agent_mode": False,
        }

    if wants_excel and not has_capability(CAP_EXCEL):
        return {
            "reply": _capability_disabled_reply(ui_language, user, "export Excel"),
            "source": "phase3",
            "intent": "export_excel_disabled",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
            "agent_mode": False,
        }

    if wants_excel:
        reply, export_dl, tn = _run_excel_export(
            db, user, session, message, ui_language=ui_language
        )
        return {
            "reply": reply,
            "source": "export",
            "intent": "export_excel",
            "tracking_number": tn,
            "llm_provider": None,
            "shipment": None,
            "export_download": export_dl,
            "agent_mode": False,
        }

    session_tns = session_tracking_numbers(db, session.id, user.id)
    kind = classify_pdf_kind(
        message,
        has_session_trackings=bool(session_tns),
        has_last_bot_reply=True,
    )

    if kind == PdfKind.tracking:
        reply, export_dl, tn = run_tracking_pdf_export(
            db, user, session, message, ui_language=ui_language
        )
        return {
            "reply": reply,
            "source": "export",
            "intent": "export_pdf",
            "tracking_number": tn,
            "llm_provider": None,
            "shipment": None,
            "export_download": export_dl,
            "agent_mode": False,
        }

    if kind == PdfKind.wrap_reply:
        reply, export_dl = run_text_pdf_export(
            db,
            user,
            session,
            message,
            user_msg_id=user_msg_id,
            ui_language=ui_language,
            use_last_bot_reply=True,
        )
        return {
            "reply": reply,
            "source": "export",
            "intent": "export_pdf",
            "tracking_number": None,
            "llm_provider": "ollama" if export_dl else None,
            "shipment": None,
            "export_download": export_dl or None,
            "agent_mode": False,
        }

    reply, export_dl = run_text_pdf_export(
        db,
        user,
        session,
        message,
        user_msg_id=user_msg_id,
        ui_language=ui_language,
        use_last_bot_reply=False,
    )
    return {
        "reply": reply,
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": None,
        "llm_provider": "ollama" if export_dl else None,
        "shipment": None,
        "export_download": export_dl or None,
        "agent_mode": False,
    }
