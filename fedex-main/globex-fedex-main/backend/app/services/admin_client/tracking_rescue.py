"""Rescue suivi FedEx admin — évite le fallback Ollama sur numéro explicite."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.activity_log_service import write_log
from app.services.admin_client.capabilities import admin_client_capability_context
from app.services.admin_client.session_bridge import (
    get_or_create_chat_session,
    persist_bot_message,
    persist_user_message,
    sync_history_from_request,
)
from app.services.client_phase12.output_guard import sanitize_client_reply
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number

logger = logging.getLogger(__name__)


def _lang(ui_language: str | None, admin: User) -> str:
    return (ui_language or admin.preferred_language or "fr").lower()[:2]


def fedex_unavailable_reply(*, lang: str = "fr") -> str:
    if lang == "en":
        return (
            "I could not query FedEx for this tracking number. "
            "Check the API connection and try again."
        )
    return (
        "Je n'ai pas pu interroger FedEx pour ce colis. "
        "Vérifiez la connexion API FedEx et réessayez."
    )


def _build_phase2_outcome(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    from app.services.chatbot_service import _compute_phase2_reply

    try:
        reply, source, intent, tn, llm_provider, shipment = _compute_phase2_reply(
            db, admin, session, message, user_msg_id, ui_language
        )
    except Exception:
        logger.exception("[admin_client] tracking rescue phase2 échec")
        return None

    return {
        "reply": reply,
        "source": source,
        "intent": intent,
        "tracking_number": tn,
        "llm_provider": llm_provider,
        "shipment": shipment,
        "export_download": None,
    }


def try_admin_tracking_rescue_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Phase 2 FedEx si le message contient un numéro de suivi explicite."""
    tn = extract_tracking_number(message or "")
    if not tn or not is_plausible_tracking_number(tn):
        return None
    return _build_phase2_outcome(db, admin, session, message, user_msg_id, ui_language)


def _finalize_kernel_result(
    db: Session,
    admin: User,
    session,
    outcome: dict[str, Any],
    *,
    message: str,
    ui_language: str | None,
    ip_address: str,
    started: float,
) -> dict[str, Any]:
    source = outcome.get("source", "admin_client")
    intent = outcome.get("intent")
    shipment = outcome.get("shipment")
    fedex_err = None
    if isinstance(shipment, dict):
        fedex_err = shipment.get("tracking_error_code") or shipment.get("error_code")
    reply = sanitize_client_reply(
        outcome.get("reply") or "",
        intent=intent,
        fedex_error_code=fedex_err,
        ui_language=ui_language,
    )
    persist_bot_message(db, session, reply, source=source)
    write_log(
        db,
        action="admin_client.chat",
        message=message[:120],
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=ip_address,
        metadata={"source": source, "intent": intent, "chat_session_id": session.id},
    )
    db.commit()
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    export_download = outcome.get("export_download")
    return {
        "reply": reply,
        "mode": "jarvis",
        "tools_used": [f"admin_client:{source}"],
        "agent_steps": [],
        "needs_approval": False,
        "approval_id": None,
        "approval_hint": None,
        "mission_id": None,
        "action_executed": bool(export_download),
        "export_download": export_download,
        "llm_degraded": False,
        "intent": intent,
        "execution_time_ms": elapsed,
        "shipment": shipment,
        "chat_session_id": session.id,
    }


def try_admin_kernel_tracking_rescue(
    db: Session,
    admin: User,
    message: str,
    *,
    conversation_history: list[Any] | None = None,
    ui_language: str = "fr",
    chat_session_id: int | None = None,
    ip_address: str = "",
    started: float | None = None,
) -> dict[str, Any] | None:
    """Dernier recours kernel : suivi FedEx live sans Ollama."""
    tn = extract_tracking_number(message or "")
    if not tn or not is_plausible_tracking_number(tn):
        return None
    if started is None:
        started = time.perf_counter()

    with admin_client_capability_context():
        try:
            session = get_or_create_chat_session(
                db, admin, chat_session_id=chat_session_id, title_hint=message
            )
            sync_history_from_request(db, session, conversation_history)
            user_msg = persist_user_message(db, session, message)
            outcome = _build_phase2_outcome(
                db, admin, session, message, user_msg.id, ui_language
            )
            if outcome is None:
                db.rollback()
                return None
            return _finalize_kernel_result(
                db,
                admin,
                session,
                outcome,
                message=message,
                ui_language=ui_language,
                ip_address=ip_address,
                started=started,
            )
        except Exception:
            db.rollback()
            logger.exception("[admin_client] kernel tracking rescue échec")
            return None


def build_tracking_error_kernel_result(
    *,
    message: str,
    ui_language: str | None,
    admin: User,
    ip_address: str = "",
    started: float | None = None,
) -> dict[str, Any]:
    """Réponse kernel déterministe quand FedEx est requis mais indisponible."""
    if started is None:
        started = time.perf_counter()
    lang = _lang(ui_language, admin)
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    return {
        "reply": fedex_unavailable_reply(lang=lang),
        "mode": "jarvis",
        "tools_used": ["admin_client:fedex_error"],
        "agent_steps": [],
        "needs_approval": False,
        "approval_id": None,
        "approval_hint": None,
        "mission_id": None,
        "action_executed": False,
        "export_download": None,
        "llm_degraded": True,
        "intent": "tracking_error",
        "execution_time_ms": elapsed,
        "shipment": None,
        "chat_session_id": None,
    }
