"""Pipeline agent e-mail admin → utilisateur (Phase 1)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.email.email_compose import compose_email_response
from app.services.admin_client.email.email_intent import classify_email_intent
from app.services.admin_client.email.email_pending import (
    is_email_cancel_message,
    is_email_confirm_message,
    is_email_send_pending,
    resolve_pending_email_action,
)
from app.services.admin_client.email.email_patterns import extract_export_token_from_history
from app.services.admin_client.email.email_service import (
    build_user_email_draft,
    resolve_recipient_user,
    search_user_by_ref,
    send_user_email,
)
from app.services.admin_client.email.email_types import (
    AdminEmailDraft,
    EmailPlan,
    EmailProfile,
    EmailTaskType,
    EmailToolError,
    PendingEmailAction,
)
from app.services.admin_client.email.email_workspace import is_email_workspace

logger = logging.getLogger(__name__)


def add_backend_metadata(
    response: dict[str, Any],
    *,
    tool_used: str,
    tools_called: list[str],
    raw_data_received: bool,
    llm_provider: str | None = None,
) -> dict[str, Any]:
    response.update(
        {
            "tool_used": tool_used,
            "tool_called": bool(tools_called),
            "tools_executed": tools_called,
            "data_source": "admin_email_service",
            "raw_data_received": raw_data_received,
            "confidence": "high" if raw_data_received else "low",
            "llm_provider": llm_provider,
            "source": "admin_email",
        }
    )
    return response


def _lang(ui_language: str | None, admin: User) -> str:
    code = (ui_language or admin.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _error_turn(lang: str, *, detail: str) -> dict[str, Any]:
    return add_backend_metadata(
        {
            "reply": compose_email_response({}, EmailPlan(task_type=EmailTaskType.ambiguous), lang=lang, error_code=detail),
            "intent": "email_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "admin_email", "status": "error", "detail": detail}],
        },
        tool_used="admin_email",
        tools_called=["admin_email"],
        raw_data_received=False,
    )


def _clarify_turn(lang: str, plan: EmailPlan) -> dict[str, Any]:
    return add_backend_metadata(
        {
            "reply": compose_email_response({}, plan, lang=lang),
            "intent": "email_clarify",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "email_intent", "status": "done", "detail": "clarify"}],
        },
        tool_used="email_intent",
        tools_called=[],
        raw_data_received=False,
    )


def _resolve_plan_recipient(db: Session, plan: EmailPlan, message: str) -> EmailPlan:
    if plan.user_id:
        return plan
    if plan.recipient_email:
        user = resolve_recipient_user(db, email=plan.recipient_email)
        if user:
            plan.user_id = user.id
        return plan
    user = search_user_by_ref(db, message)
    if user:
        plan.user_id = user.id
        plan.recipient_email = user.email
    return plan


def _draft_from_pending(
    db: Session,
    admin: User,
    pending: PendingEmailAction,
    *,
    lang: str,
) -> AdminEmailDraft:
    attachment_bytes = None
    attachment_filename = None
    attachment_mime = "application/pdf"
    if pending.attachment_export_token:
        from app.services.admin_client.email.email_service import _load_attachment

        attachment_bytes, attachment_filename, attachment_mime = _load_attachment(
            pending.attachment_export_token,
            owner_id=admin.id,
        )
    return AdminEmailDraft(
        to=pending.to,
        subject=pending.subject,
        body_text=pending.body_text,
        user_id=pending.user_id,
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_filename,
        attachment_mime=attachment_mime,
    )


def _handle_action_email_offer(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    history_text: str | None,
    conversation_history: list[Any] | None,
    chat_session_id: int | None = None,
) -> dict[str, Any] | None:
    from app.services.admin_client.email.email_action_hooks import build_draft_turn_from_offer
    from app.services.admin_client.email.email_action_offer import (
        is_action_email_offer_accept,
        is_action_email_offer_decline,
        is_action_email_offer_pending,
        resolve_action_email_offer,
    )
    from app.services.admin_client.pending_resolver import is_latest_pending_kind

    if not is_latest_pending_kind(
        "email_offer",
        db=db,
        chat_session_id=chat_session_id,
        conversation_history=conversation_history,
    ):
        return None

    if not is_action_email_offer_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    if is_action_email_offer_decline(message):
        decline = (
            "D'accord — aucun e-mail ne sera envoyé à l'utilisateur."
            if lang == "fr"
            else "OK — no email will be sent to the user."
        )
        return add_backend_metadata(
            {
                "reply": decline,
                "intent": "email_offer_declined",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "action_email_offer", "status": "declined", "detail": None}],
            },
            tool_used="action_email_offer",
            tools_called=[],
            raw_data_received=False,
        )

    if not is_action_email_offer_accept(message):
        return None

    offer = resolve_action_email_offer(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    )
    if not offer:
        return _error_turn(lang, detail="pending_parse_failed")

    return build_draft_turn_from_offer(db, admin, offer, lang=lang)


def _handle_email_clarify_followup(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    history_text: str | None,
    conversation_history: list[Any] | None,
    chat_session_id: int | None = None,
) -> dict[str, Any] | None:
    from app.services.admin_client.email.email_followup import (
        extract_admin_note_from_clarify_reply,
        extract_recipient_from_history,
        is_email_clarify_followup,
        is_suspend_email_clarify_context,
    )

    hist = history_text or ""
    if not is_email_clarify_followup(
        message,
        history_text=hist,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    # Combo suspend+mail : laisser l'agent utilisateurs récupérer le fil.
    if is_suspend_email_clarify_context(hist):
        return None

    recipient = extract_recipient_from_history(hist)
    if not recipient:
        return None

    admin_note = extract_admin_note_from_clarify_reply(message)
    plan = EmailPlan(
        task_type=EmailTaskType.send_user_email,
        profile=EmailProfile.DRAFT,
        recipient_email=recipient,
        admin_note=admin_note,
        raw_matches=["email_clarify_followup"],
    )
    plan = _resolve_plan_recipient(db, plan, message)
    if not plan.user_id and not plan.recipient_email:
        return _error_turn(lang, detail="user_not_found")

    try:
        draft = build_user_email_draft(db, admin, plan, lang=lang)
    except EmailToolError as exc:
        return _error_turn(lang, detail=str(exc))

    plan.profile = EmailProfile.CONFIRM
    reply = compose_email_response({}, plan, lang=lang, draft=draft)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "email_draft",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "compose_user_email", "status": "done", "detail": draft.to}],
        },
        tool_used="compose_user_email",
        tools_called=["compose_user_email"],
        raw_data_received=True,
    )


def _handle_email_confirm(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    history_text: str | None,
    conversation_history: list[Any] | None,
    chat_session_id: int | None = None,
    ip_address: str = "",
) -> dict[str, Any] | None:
    from app.services.admin_client.pending_resolver import is_latest_pending_kind

    if not is_latest_pending_kind(
        "email_send",
        db=db,
        chat_session_id=chat_session_id,
        conversation_history=conversation_history,
    ):
        return None

    if not is_email_send_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    if is_email_cancel_message(message):
        cancel = (
            "Envoi annulé — aucun e-mail transmis."
            if lang == "fr"
            else "Send cancelled — no email was sent."
        )
        return add_backend_metadata(
            {
                "reply": cancel,
                "intent": "email_send_cancelled",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "send_user_email", "status": "cancelled", "detail": None}],
            },
            tool_used="send_user_email",
            tools_called=[],
            raw_data_received=False,
        )

    if not is_email_confirm_message(message):
        return None

    pending = resolve_pending_email_action(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    )
    if not pending:
        return _error_turn(lang, detail="pending_parse_failed")

    try:
        draft = _draft_from_pending(db, admin, pending, lang=lang)
        result = send_user_email(db, admin, draft, ip_address=ip_address)
    except EmailToolError as exc:
        return _error_turn(lang, detail=str(exc))

    plan = EmailPlan(task_type=EmailTaskType.send_user_email, profile=EmailProfile.DONE)
    reply = compose_email_response({}, plan, lang=lang, send_result=result)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "email_send_done",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "send_user_email", "status": "done", "detail": pending.to}],
        },
        tool_used="send_user_email",
        tools_called=["send_user_email"],
        raw_data_received=True,
    )


def run_email_pipeline(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    ip_address: str = "",
) -> dict[str, Any] | None:
    from app.services.admin_client.intent_priority import should_route_email

    text = (message or "").strip()
    lang = _lang(ui_language, admin)
    hist = history_text or ""

    confirm_turn = _handle_email_confirm(
        db,
        admin,
        text,
        lang=lang,
        history_text=hist,
        conversation_history=conversation_history,
        chat_session_id=getattr(session, "id", None),
        ip_address=ip_address,
    )
    if confirm_turn is not None:
        return confirm_turn

    offer_turn = _handle_action_email_offer(
        db,
        admin,
        text,
        lang=lang,
        history_text=hist,
        conversation_history=conversation_history,
        chat_session_id=getattr(session, "id", None),
    )
    if offer_turn is not None:
        return offer_turn

    clarify_turn = _handle_email_clarify_followup(
        db,
        admin,
        text,
        lang=lang,
        history_text=hist,
        conversation_history=conversation_history,
        chat_session_id=getattr(session, "id", None),
    )
    if clarify_turn is not None:
        return clarify_turn

    from app.services.admin_client.email.email_followup import (
        is_email_clarify_followup,
        is_suspend_email_clarify_context,
    )

    if is_email_clarify_followup(
        text,
        history_text=hist,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=getattr(session, "id", None),
    ) and is_suspend_email_clarify_context(hist):
        return None

    if not should_route_email(text, history_text=hist):
        return None

    plan = classify_email_intent(text, history_text=hist, lang=lang)
    if plan.task_type == EmailTaskType.ambiguous:
        if is_email_workspace(text, history_text=hist):
            plan = EmailPlan(
                task_type=EmailTaskType.send_user_email,
                profile=EmailProfile.CLARIFY,
                needs_clarification=True,
                clarification_question=plan.clarification_question
                or (
                    "À qui envoyer l'e-mail et quel message ?"
                    if lang == "fr"
                    else "Who should receive the email and what message?"
                ),
            )
            return _clarify_turn(lang, plan)
        return None

    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    plan = _resolve_plan_recipient(db, plan, text)
    if not plan.user_id and not plan.recipient_email:
        plan.needs_clarification = True
        plan.profile = EmailProfile.CLARIFY
        plan.clarification_question = (
            "Quel utilisateur doit recevoir l'e-mail (adresse ou #id) ?"
            if lang == "fr"
            else "Which user should receive the email (address or #id)?"
        )
        return _clarify_turn(lang, plan)

    if not plan.attachment_export_token:
        token = extract_export_token_from_history(hist)
        if token:
            plan.attachment_export_token = token

    try:
        draft = build_user_email_draft(db, admin, plan, lang=lang)
    except EmailToolError as exc:
        return _error_turn(lang, detail=str(exc))

    plan.profile = EmailProfile.CONFIRM
    reply = compose_email_response({}, plan, lang=lang, draft=draft)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "email_draft",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "compose_user_email", "status": "done", "detail": draft.to}],
        },
        tool_used="compose_user_email",
        tools_called=["compose_user_email"],
        raw_data_received=True,
    )
