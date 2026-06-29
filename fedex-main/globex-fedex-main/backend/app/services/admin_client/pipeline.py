"""Pipeline admin_client — réutilise le flux client live côté admin.

Reproduit l'orchestration de `chatbot_service.process_user_message` (documents,
notifications, PDF/Excel, suivi FedEx) en appelant directement les modules client,
mais :
- s'appuie sur une `ChatSession` miroir attachée à l'admin (session_bridge) ;
- n'intercepte que les tours « capacités client » (suivi, export, document,
  notification) et renvoie `None` sinon pour laisser le kernel admin (Ollama + outils
  plateforme) gérer le reste ;
- active temporairement les capacités client requises sans modifier le portail client.

Les écritures se font dans un SAVEPOINT : si aucun handler client ne répond, on annule
proprement (pas de session/message orphelin) et on rend la main au kernel.
"""

from __future__ import annotations

import logging
import re
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
from app.services.chat_session_context import (
    build_conversation_history_for_llm,
    resolve_tracking_for_message,
    resolve_tracking_from_history_text,
)
from app.services.chat_shipment_reply import is_session_follow_up
from app.services.client_phase3.excel_postprocess import (
    handle_excel_only_followup_turn,
    is_excel_only_followup,
    maybe_attach_excel_export,
    wants_excel_format,
)
from app.services.client_phase3.pdf_postprocess import (
    handle_conversation_pdf_turn,
    is_pdf_only_followup,
    maybe_attach_pdf_export,
    wants_pdf_format,
)
from app.services.admin_client.dashboard import try_admin_dashboard_turn
from app.services.admin_client.reports.reports_executor import try_admin_reports_turn
from app.services.admin_client.logs.logs_executor import try_admin_logs_turn
from app.services.admin_client.security.security_executor import try_admin_security_turn
from app.services.admin_client.users.users_executor import try_admin_users_turn
from app.services.admin_client.pending_confirm import try_admin_pending_confirm_turn
from app.services.admin_client.tickets.tickets_executor import try_admin_tickets_turn
from app.services.admin_client.email.email_executor import try_admin_email_turn
from app.services.admin_client.intent_priority import (
    should_route_dashboard,
    should_route_document_followup,
    should_route_email,
    should_route_reports,
    should_route_security,
    should_route_logs,
    should_route_tickets,
    should_route_users,
)
from app.services.admin_client.admin_pdf_router import try_admin_shipment_pdf_turn
from app.services.admin_client.pdf_clarify_followup import (
    is_pdf_clarify_choice_message,
    is_pdf_clarify_pending,
    is_pdf_clarify_pending_from_history,
    is_pdf_clarify_pending_in_session,
    try_admin_pdf_clarify_choice_turn,
)
from app.services.admin_client.notifications_adapter import (
    is_mark_read_intent,
    try_admin_notifications_turn,
)
from app.services.admin_client.pdf_free_text import try_admin_free_text_pdf_turn
from app.services.admin_client.tracking_rescue import (
    fedex_unavailable_reply,
    try_admin_tracking_rescue_turn,
)
from app.services.client_phase5.notification_filters import is_notification_workspace
from app.services.client_phase9.capabilities import has_document_read_capability
from app.services.client_phase9.document_reader import resolve_attachment, try_document_read_turn
from app.services.client_phase9.document_session import (
    is_document_followup_question,
    try_document_followup_turn,
)
from app.services.client_phase12.output_guard import sanitize_client_reply
from app.services.llm.intent_detection import is_general_logistics_question
from app.services.llm.tracking_extract import extract_tracking_number
from app.services.message_attachment import normalize_attachment_mime
from app.utils.tracking_parser import is_plausible_tracking_number

logger = logging.getLogger(__name__)


def _history_text(conversation_history: list[Any] | None) -> str:
    lines: list[str] = []
    for raw in conversation_history or []:
        if isinstance(raw, dict):
            content = str(raw.get("content") or "").strip()
        else:
            content = str(getattr(raw, "content", "") or "").strip()
        if content:
            lines.append(content)
    return "\n".join(lines)


def _should_engage(
    message: str,
    *,
    has_attachment: bool,
    history_text: str,
    conversation_history: list[Any] | None = None,
) -> bool:
    """Décide si le tour relève d'une capacité client (sinon kernel admin)."""
    if has_attachment:
        return True
    if is_document_followup_question(message):
        return True
    if is_notification_workspace(message):
        return True
    if is_mark_read_intent(message) and re.search(r"notif", message, re.IGNORECASE):
        return True
    if is_pdf_clarify_choice_message(message) and is_pdf_clarify_pending_from_history(
        conversation_history
    ):
        return True
    if should_route_dashboard(message, history_text=history_text):
        return True
    from app.services.admin_client.reports.reports_share_pending import is_share_pending

    if is_share_pending(conversation_history=conversation_history):
        return True
    from app.services.admin_client.email.email_pending import is_email_send_pending

    if is_email_send_pending(
        conversation_history=conversation_history,
        history_text=history_text,
    ):
        return True
    from app.services.admin_client.email.email_followup import is_email_clarify_pending

    if is_email_clarify_pending(
        conversation_history=conversation_history,
        history_text=history_text,
    ):
        return True
    from app.services.admin_client.email.email_action_offer import is_action_email_offer_pending

    if is_action_email_offer_pending(
        conversation_history=conversation_history,
        history_text=history_text,
    ):
        return True
    if should_route_email(message, history_text=history_text):
        return True
    if should_route_reports(message, history_text=history_text):
        return True
    from app.services.admin_client.security.security_followup import is_security_followup_message

    if is_security_followup_message(message, history_text=history_text):
        return True
    from app.services.admin_client.security.security_pdf import is_security_pdf_followup

    if is_security_pdf_followup(message, history_text=history_text):
        return True
    if should_route_security(message, history_text=history_text):
        return True
    from app.services.admin_client.logs.logs_pending import is_logs_action_pending
    from app.services.admin_client.logs.logs_followup import is_logs_followup_message
    from app.services.admin_client.logs.logs_export import (
        is_logs_excel_followup,
        is_logs_pdf_followup,
    )

    if is_logs_action_pending(
        conversation_history=conversation_history,
        history_text=history_text,
    ):
        return True
    if is_logs_followup_message(message, history_text=history_text):
        return True
    if is_logs_excel_followup(message, history_text=history_text):
        return True
    if is_logs_pdf_followup(message, history_text=history_text):
        return True
    if should_route_logs(message, history_text=history_text):
        return True
    from app.services.admin_client.users.users_pending import is_users_action_pending

    if is_users_action_pending(
        conversation_history=conversation_history,
        history_text=history_text,
    ):
        return True
    if should_route_users(message, history_text=history_text):
        return True
    from app.services.admin_client.tickets.tickets_followup import is_tickets_followup_message
    from app.services.admin_client.tickets.tickets_pending import is_tickets_action_pending

    if is_tickets_action_pending(
        conversation_history=conversation_history,
        history_text=history_text,
    ):
        return True
    if is_tickets_followup_message(message, history_text=history_text):
        return True
    if should_route_tickets(message, history_text=history_text):
        return True
    if wants_pdf_format(message) or wants_excel_format(message):
        return True
    if is_pdf_only_followup(message) or is_excel_only_followup(message):
        return True

    tn = extract_tracking_number(message)
    if tn and is_plausible_tracking_number(tn):
        return True
    # Relance contextuelle (« montre la carte », « plus d'info ») référant un colis du fil.
    if is_session_follow_up(message) and resolve_tracking_from_history_text(history_text):
        return True
    return False


def _dispatch(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    attachment,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Cascade des handlers client. Renvoie un dict réponse ou None (pas de match client)."""
    from app.services.chatbot_service import _compute_phase2_reply

    if attachment is not None and has_document_read_capability():
        doc = try_document_read_turn(
            db,
            admin,
            session,
            message,
            user_msg_id,
            attachment=attachment,
            ui_language=ui_language,
            compute_phase2_reply=_compute_phase2_reply,
        )
        if doc is not None:
            return doc

    notif = try_admin_notifications_turn(db, admin, session, message, user_msg_id, ui_language)
    if notif is not None:
        return notif

    history = build_conversation_history_for_llm(
        db, session_id=session.id, exclude_message_id=user_msg_id, limit=6
    )
    history_text = _history_text(history)

    pending_turn = try_admin_pending_confirm_turn(
        db,
        admin,
        session,
        message,
        ui_language,
        history_text=history_text,
        conversation_history=history,
    )
    if pending_turn is not None:
        return pending_turn

    dash = try_admin_dashboard_turn(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
    )
    if dash is not None:
        return dash

    email_turn = try_admin_email_turn(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
        conversation_history=history,
    )
    if email_turn is not None:
        return email_turn

    reports = try_admin_reports_turn(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
        conversation_history=history,
    )
    if reports is not None:
        return reports

    security = try_admin_security_turn(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
        conversation_history=history,
    )
    if security is not None:
        return security

    logs = try_admin_logs_turn(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
        conversation_history=history,
    )
    if logs is not None:
        return logs

    tickets = try_admin_tickets_turn(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
        conversation_history=history,
    )
    if tickets is not None:
        return tickets

    users = try_admin_users_turn(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
        conversation_history=history,
    )
    if users is not None:
        return users

    early = (
        try_admin_pdf_clarify_choice_turn(
            db, admin, session, message, user_msg_id, ui_language
        )
        or handle_excel_only_followup_turn(db, admin, session, message, ui_language)
        or handle_conversation_pdf_turn(db, admin, session, message, user_msg_id, ui_language)
        or try_admin_shipment_pdf_turn(
            db, admin, session, message, user_msg_id, ui_language
        )
        or try_admin_free_text_pdf_turn(
            db, admin, session, message, user_msg_id, ui_language
        )
    )
    if early is not None:
        return early

    if has_document_read_capability() and should_route_document_followup(message):
        doc = try_document_followup_turn(
            db,
            admin,
            session,
            message,
            user_msg_id,
            ui_language=ui_language,
            compute_phase2_reply=_compute_phase2_reply,
        )
        if doc is not None:
            return doc

    history = build_conversation_history_for_llm(
        db, session_id=session.id, exclude_message_id=user_msg_id, limit=4
    )
    tracking_number = extract_tracking_number(message)
    if tracking_number and not is_plausible_tracking_number(tracking_number):
        tracking_number = None
    if not tracking_number:
        tracking_number, _src = resolve_tracking_for_message(
            db,
            session_id=session.id,
            user_id=admin.id,
            message=message,
            conversation_history=history,
        )
    if (
        tracking_number
        and not extract_tracking_number(message)
        and is_general_logistics_question(message)
    ):
        tracking_number = None
    if not tracking_number:
        rescue = try_admin_tracking_rescue_turn(
            db, admin, session, message, user_msg_id, ui_language
        )
        if rescue is not None:
            return rescue
        return None

    lang = (ui_language or admin.preferred_language or "fr").lower()[:2]
    try:
        reply, source, intent, tn, llm_provider, shipment = _compute_phase2_reply(
            db, admin, session, message, user_msg_id, ui_language
        )
    except Exception:
        logger.exception("[admin_client] phase2 FedEx échec")
        return {
            "reply": fedex_unavailable_reply(lang=lang),
            "source": "admin_client",
            "intent": "tracking_error",
            "tracking_number": tracking_number,
            "llm_provider": None,
            "shipment": None,
            "export_download": None,
        }
    export_download: dict[str, Any] | None = None
    if wants_pdf_format(message):
        reply, pdf_dl, pdf_intent = maybe_attach_pdf_export(
            db, admin, session, message, user_msg_id, ui_language,
            chat_reply=reply, tracking_number=tn,
        )
        if pdf_dl:
            export_download = pdf_dl
        if pdf_intent:
            intent = pdf_intent
    if wants_excel_format(message) and not wants_pdf_format(message):
        reply, xlsx_dl, xlsx_intent = maybe_attach_excel_export(
            db, admin, session, message, user_msg_id, ui_language,
            chat_reply=reply, tracking_number=tn,
        )
        if xlsx_dl:
            export_download = xlsx_dl
        if xlsx_intent:
            intent = xlsx_intent

    return {
        "reply": reply,
        "source": source,
        "intent": intent,
        "tracking_number": tn,
        "llm_provider": llm_provider,
        "shipment": shipment,
        "export_download": export_download,
    }


def _gate_history_text(
    db: Session,
    *,
    chat_session_id: int | None,
    conversation_history: list[Any] | None,
) -> str:
    """Historique pour la gate — payload client puis repli session DB."""
    text = _history_text(conversation_history)
    if text or not chat_session_id:
        return text
    try:
        from app.services.chat_session_context import build_conversation_history_for_llm

        db_hist = build_conversation_history_for_llm(
            db, session_id=chat_session_id, limit=8
        )
        return _history_text(db_hist)
    except Exception:
        return text


def run_admin_client_turn(
    db: Session,
    admin: User,
    message: str,
    *,
    conversation_history: list[Any] | None = None,
    ui_language: str = "fr",
    chat_session_id: int | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    file_name: str | None = None,
    ip_address: str = "",
    started: float | None = None,
) -> dict[str, Any] | None:
    """Tour admin réutilisant le flux client. Renvoie un dict kernel ou None."""
    if started is None:
        started = time.perf_counter()
    message = (message or "").strip()
    b64 = (image_base64 or "").strip() or None

    with admin_client_capability_context():
        mime = normalize_attachment_mime(image_mime_type) if b64 else None
        attachment = resolve_attachment(
            attachment_base64=b64,
            attachment_mime_type=mime,
            file_name=file_name,
        )
        has_attachment = attachment is not None

        if not message and not has_attachment:
            return None
        gate_history = _gate_history_text(
            db, chat_session_id=chat_session_id, conversation_history=conversation_history
        )
        engage = _should_engage(
            message,
            has_attachment=has_attachment,
            history_text=gate_history,
            conversation_history=conversation_history,
        )
        if (
            not engage
            and is_pdf_clarify_choice_message(message)
            and chat_session_id
        ):
            engage = is_pdf_clarify_pending_in_session(db, chat_session_id)
        if not engage and chat_session_id:
            from app.services.admin_client.email.email_pending import (
                is_email_confirm_message,
                is_email_cancel_message,
                is_email_send_pending,
            )
            from app.services.admin_client.reports.reports_share_pending import (
                is_share_cancel_message,
                is_share_confirm_message,
                is_share_pending,
            )

            if (is_email_confirm_message(message) or is_email_cancel_message(message)) and (
                is_email_send_pending(db=db, chat_session_id=chat_session_id)
            ):
                engage = True
            if (is_share_confirm_message(message) or is_share_cancel_message(message)) and (
                is_share_pending(db=db, chat_session_id=chat_session_id)
            ):
                engage = True
            from app.services.admin_client.users.users_pending import (
                is_users_action_pending_in_session,
                is_users_cancel_message,
                is_users_confirm_message,
            )

            if (is_users_confirm_message(message) or is_users_cancel_message(message)) and (
                is_users_action_pending_in_session(db, chat_session_id)
            ):
                engage = True
            from app.services.admin_client.tickets.tickets_pending import (
                is_tickets_action_pending_in_session,
                is_tickets_cancel_message,
                is_tickets_confirm_message,
            )

            if (is_tickets_confirm_message(message) or is_tickets_cancel_message(message)) and (
                is_tickets_action_pending_in_session(db, chat_session_id)
            ):
                engage = True
            from app.services.admin_client.logs.logs_pending import (
                is_logs_action_pending_in_session,
                is_logs_cancel_message,
                is_logs_confirm_message,
            )

            if (is_logs_confirm_message(message) or is_logs_cancel_message(message)) and (
                is_logs_action_pending_in_session(db, chat_session_id)
            ):
                engage = True
        if not engage:
            return None

        # Pas de SAVEPOINT : certains handlers client committent en interne. Si aucun
        # handler ne répond (outcome None), on annule les écritures (session/message)
        # avant de rendre la main au kernel.
        try:
            session = get_or_create_chat_session(
                db, admin, chat_session_id=chat_session_id, title_hint=message
            )
            sync_history_from_request(db, session, conversation_history)
            user_msg = persist_user_message(
                db,
                session,
                message,
                image_base64=b64,
                image_mime_type=mime,
                file_name=file_name,
            )
            outcome = _dispatch(
                db, admin, session, message, user_msg.id, attachment, ui_language
            )
        except Exception:
            db.rollback()
            logger.exception("[admin_client] pipeline échec")
            tn = extract_tracking_number(message)
            if (
                _should_engage(
                    message,
                    has_attachment=has_attachment,
                    history_text=_history_text(conversation_history),
                    conversation_history=conversation_history,
                )
                and tn
                and is_plausible_tracking_number(tn)
            ):
                lang = (ui_language or admin.preferred_language or "fr").lower()[:2]
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
            return None

        if outcome is None:
            db.rollback()
            return None

        source = outcome.get("source", "admin_client")
        intent = outcome.get("intent")
        fedex_err = None
        shipment = outcome.get("shipment")
        if isinstance(shipment, dict):
            fedex_err = shipment.get("tracking_error_code") or shipment.get("error_code")
        reply = sanitize_client_reply(
            outcome.get("reply") or "",
            intent=intent,
            fedex_error_code=fedex_err,
            ui_language=ui_language,
        )
        persist_bot_message(db, session, reply, source=source)

        export_download = outcome.get("export_download")
        write_log(
            db,
            action=(
                "admin_dashboard.tool"
                if source == "admin_dashboard"
                else "admin_reports.tool"
                if source == "admin_reports"
                else "admin_client.chat"
            ),
            message=message[:120],
            category="admin",
            level="INFO",
            actor_user_id=admin.id,
            ip_address=ip_address,
            metadata={
                "source": source,
                "intent": intent,
                "chat_session_id": session.id,
                "tool_used": outcome.get("tool_used"),
                "confidence": outcome.get("confidence"),
            },
        )
        db.commit()

        elapsed = round((time.perf_counter() - started) * 1000, 1)
        agent_steps = outcome.get("agent_steps") or []
        return {
            "reply": reply,
            "mode": "jarvis",
            "tools_used": [f"admin_client:{source}"],
            "agent_steps": agent_steps,
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
            "tool_used": outcome.get("tool_used"),
            "tool_called": outcome.get("tool_called"),
            "data_source": outcome.get("data_source"),
            "raw_data_received": outcome.get("raw_data_received"),
            "confidence": outcome.get("confidence"),
        }
