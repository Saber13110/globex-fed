"""Pipeline agent Tickets admin — lecture + écritures phase 2."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.tickets import tickets_service, tickets_tool
from app.services.admin_client.tickets.tickets_compose import compose_tickets_response
from app.services.admin_client.tickets.tickets_intent import (
    TargetTicketResolution,
    classify_tickets_intent,
    clarify_missing_reply_body,
    default_clarify_plan,
    resolve_target_ticket,
)
from app.services.admin_client.tickets.tickets_narrative import draft_ticket_reply
from app.services.admin_client.tickets.tickets_pending import (
    is_tickets_action_pending,
    is_tickets_cancel_message,
    is_tickets_confirm_message,
    resolve_pending_ticket_action,
)
from app.services.admin_client.tickets.tickets_reconcile import reconcile_tickets_plan
from app.services.admin_client.tickets.tickets_types import (
    TicketsPlan,
    TicketsProfile,
    TicketsTaskType,
    TicketsToolError,
)
from app.services.admin_client.tickets.tickets_workspace import is_tickets_workspace
from app.services.admin_client.tickets.tickets_followup import (
    merge_tickets_history_text,
    resolve_ticket_id_from_context,
)

logger = logging.getLogger(__name__)

_WRITE_TASKS = frozenset({
    TicketsTaskType.ticket_reply,
    TicketsTaskType.ticket_resolve,
})

_FETCH_ERROR_FR = (
    "Je n'ai pas pu récupérer les tickets support en temps réel. "
    "Je ne peux pas donner une réponse fiable."
)
_FETCH_ERROR_EN = "I could not fetch live support ticket data. I cannot provide a reliable answer."


@dataclass
class ToolExecutionResult:
    ok: bool
    processed: dict[str, Any] = field(default_factory=dict)
    tools_called: list[str] = field(default_factory=list)
    error: str | None = None


def detect_intent(
    message: str,
    *,
    ui_language: str = "fr",
    history_text: str | None = None,
) -> TicketsPlan | None:
    lang = (ui_language or "fr").lower()[:2]
    if lang not in {"fr", "en"}:
        lang = "fr"

    plan = classify_tickets_intent(message, history_text=history_text or "", lang=lang)
    if plan.needs_clarification:
        return plan
    if plan.task_type == TicketsTaskType.ambiguous:
        if is_tickets_workspace(message, history_text=history_text or ""):
            return default_clarify_plan(lang)
        return None
    return reconcile_tickets_plan(message, plan, history_text=history_text or "")


def _apply_target(plan: TicketsPlan, resolution: TargetTicketResolution) -> TicketsPlan | None:
    if resolution.needs_clarification:
        plan.needs_clarification = True
        plan.clarification_question = resolution.clarification_question
        plan.clarification_candidates = resolution.candidates or []
        plan.profile = TicketsProfile.CLARIFY
        return plan
    if resolution.ticket_id:
        plan.ticket_id = resolution.ticket_id
    return plan


def execute_tools(db: Session, plan: TicketsPlan) -> ToolExecutionResult:
    tools_called: list[str] = []
    processed: dict[str, Any] = {}

    try:
        if plan.task_type == TicketsTaskType.ticket_list:
            tools_called.append("list_tickets")
            tickets = tickets_tool.list_tickets(db, plan)
            processed = {
                "tickets": tickets,
                "filters": {
                    "status": plan.status_filter,
                    "priority": plan.priority_filter,
                    "category": plan.category_filter,
                    "search": plan.search_query,
                },
            }
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == TicketsTaskType.ticket_summary:
            tools_called.append("summarize_tickets")
            summary = tickets_tool.build_summary(db, plan)
            processed = {
                "summary": summary,
                "tickets": summary.get("tickets") or [],
                "filters": {
                    "status": plan.status_filter,
                    "priority": plan.priority_filter,
                    "category": plan.category_filter,
                    "search": plan.search_query,
                },
            }
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == TicketsTaskType.ticket_details_batch:
            tools_called.append("get_tickets_details_batch")
            batch = tickets_tool.build_details_batch(db, plan)
            processed = {
                "details": batch.get("details") or [],
                "tickets": batch.get("tickets") or [],
                "filters": {
                    "status": plan.status_filter,
                    "priority": plan.priority_filter,
                    "category": plan.category_filter,
                    "search": plan.search_query,
                },
            }
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        needs_ticket = plan.task_type in {TicketsTaskType.ticket_detail, *_WRITE_TASKS}
        if needs_ticket:
            if not plan.ticket_id:
                return ToolExecutionResult(ok=False, error="ticket_not_specified", tools_called=tools_called)
            tools_called.append("get_ticket_detail")
            processed["ticket"] = tickets_tool.get_ticket_detail(db, int(plan.ticket_id))
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        return ToolExecutionResult(ok=False, error="unknown_task", tools_called=tools_called)
    except TicketsToolError as exc:
        return ToolExecutionResult(ok=False, error=str(exc), tools_called=tools_called)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tickets execute_tools failed: %s", exc)
        return ToolExecutionResult(ok=False, error="fetch_failed", tools_called=tools_called)


def execute_confirmed_ticket_action(
    db: Session,
    admin: User,
    pending_action: str,
    ticket_id: int,
    payload: dict[str, str],
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    if pending_action == "reply":
        body = (payload.get("reply_body") or "").strip()
        if not body:
            raise TicketsToolError("empty_reply")
        return tickets_service.reply_to_ticket(
            db, ticket_id, admin.id, body, ip_address=ip_address
        )
    if pending_action == "resolve":
        status = (payload.get("target_status") or "resolved").strip().lower()
        return tickets_service.set_ticket_status(
            db, ticket_id, admin.id, status, ip_address=ip_address
        )
    raise TicketsToolError("unknown_action")


def _task_from_pending_action(action: str) -> TicketsTaskType:
    if action == "reply":
        return TicketsTaskType.ticket_reply
    if action == "resolve":
        return TicketsTaskType.ticket_resolve
    return TicketsTaskType.ambiguous


def intent_for_task(task: TicketsTaskType) -> str:
    return {
        TicketsTaskType.ticket_list: "tickets_list",
        TicketsTaskType.ticket_detail: "tickets_detail",
        TicketsTaskType.ticket_details_batch: "tickets_details_batch",
        TicketsTaskType.ticket_summary: "tickets_summary",
        TicketsTaskType.ticket_reply: "tickets_reply",
        TicketsTaskType.ticket_resolve: "tickets_resolve",
    }.get(task, "tickets_query")


def add_backend_metadata(
    response: dict[str, Any],
    *,
    tool_used: str,
    tools_called: list[str],
    raw_data_received: bool,
    llm_provider: str | None = None,
) -> dict[str, Any]:
    conf = "high" if raw_data_received else "low"
    response.update(
        {
            "tool_used": tool_used,
            "tool_called": bool(tools_called),
            "tools_executed": tools_called,
            "data_source": "admin_support_api",
            "raw_data_received": raw_data_received,
            "confidence": conf,
            "llm_provider": llm_provider,
            "source": "admin_tickets",
        }
    )
    return response


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _error_turn(lang: str, *, detail: str) -> dict[str, Any]:
    from app.services.admin_client.tickets.tickets_compose import _error_text

    known = {
        "ticket_not_found", "fetch_failed", "ticket_not_specified",
        "ticket_closed", "empty_reply", "reply_failed", "invalid_status",
        "unknown_action", "pending_parse_failed",
    }
    reply = _error_text(detail, lang) if detail in known else (
        _FETCH_ERROR_EN if lang == "en" else _FETCH_ERROR_FR
    )
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "tickets_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "tickets_service", "status": "error", "detail": detail}],
        },
        tool_used="tickets_service",
        tools_called=["tickets_service"],
        raw_data_received=False,
    )


def _clarify_turn(lang: str, plan: TicketsPlan) -> dict[str, Any]:
    reply = compose_tickets_response({}, plan, lang=lang)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "tickets_clarify",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "tickets_intent", "status": "done", "detail": "clarify"}],
        },
        tool_used="tickets_intent",
        tools_called=[],
        raw_data_received=False,
    )


def _handle_ticket_action_confirm(
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
    if not is_tickets_action_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    if is_tickets_cancel_message(message):
        cancel = (
            "Action annulée — aucune modification sur le ticket."
            if lang == "fr"
            else "Action cancelled — no ticket changes made."
        )
        return add_backend_metadata(
            {
                "reply": cancel,
                "intent": "tickets_action_cancelled",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "tickets_action", "status": "cancelled", "detail": None}],
            },
            tool_used="tickets_action",
            tools_called=[],
            raw_data_received=False,
        )

    if not is_tickets_confirm_message(message):
        return None

    pending = resolve_pending_ticket_action(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    )
    if not pending:
        return _error_turn(lang, detail="pending_parse_failed")

    try:
        result = execute_confirmed_ticket_action(
            db,
            admin,
            pending.action,
            pending.ticket_id,
            pending.payload,
            ip_address=ip_address,
        )
    except TicketsToolError as exc:
        return _error_turn(lang, detail=str(exc))

    task = _task_from_pending_action(pending.action)
    plan = TicketsPlan(
        task_type=task,
        profile=TicketsProfile.DONE,
        ticket_id=pending.ticket_id,
        target_status=pending.payload.get("target_status", "resolved"),
    )
    processed: dict[str, Any] = {}
    try:
        processed["ticket"] = tickets_tool.get_ticket_detail(db, pending.ticket_id)
    except TicketsToolError:
        processed["ticket"] = {"id": pending.ticket_id, "subject": result.get("subject")}
    reply = compose_tickets_response(processed, plan, lang=lang, action_result=result)

    from app.services.admin_client.email.email_action_hooks import (
        apply_post_action_email_hook,
        build_admin_note_for_ticket_action,
        scenario_for_ticket_action,
        should_offer_email_after_ticket_action,
    )

    scenario = scenario_for_ticket_action(pending.action)
    if scenario and (
        should_offer_email_after_ticket_action(pending.action)
        or pending.payload.get("notify_email") == "true"
    ):
        ticket_row = processed.get("ticket") or {}
        user_id = int(ticket_row.get("user_id") or 0)
        if not user_id:
            from app.models.support_ticket import SupportTicket

            ticket_obj = db.get(SupportTicket, pending.ticket_id)
            user_id = int(ticket_obj.user_id) if ticket_obj else 0
        if user_id:
            recipient_email = str(ticket_row.get("user_email") or "")
            ticket_subject = str(ticket_row.get("subject") or result.get("subject") or "")
            admin_note = build_admin_note_for_ticket_action(
                pending.action,
                ticket_subject=ticket_subject,
                reply_body=pending.payload.get("reply_body", ""),
                lang=lang,
            )
            notify_inline = pending.payload.get("notify_email") == "true"
            hook_result = apply_post_action_email_hook(
                db,
                admin,
                reply,
                user_id=user_id,
                scenario=scenario,
                admin_note=admin_note,
                ticket_id=pending.ticket_id,
                ticket_subject=ticket_subject,
                recipient_email=recipient_email,
                notify_inline=notify_inline,
                lang=lang,
            )
            if isinstance(hook_result, dict):
                return hook_result
            reply = hook_result

    return add_backend_metadata(
        {
            "reply": reply,
            "intent": f"tickets_{pending.action}_done",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": pending.action, "status": "done", "detail": None}],
        },
        tool_used=pending.action,
        tools_called=[pending.action],
        raw_data_received=True,
    )


def _resolve_ticket_target(
    db: Session,
    text: str,
    plan: TicketsPlan,
    *,
    merged_history: str,
    lang: str,
) -> TicketsPlan | None:
    if plan.task_type not in {TicketsTaskType.ticket_detail, *_WRITE_TASKS}:
        return plan

    resolution = resolve_target_ticket(db, text, plan, history_text=merged_history, lang=lang)
    clarified = _apply_target(plan, resolution)
    if clarified and clarified.needs_clarification:
        return clarified

    if plan.ticket_id:
        resolved = resolve_ticket_id_from_context(
            db, int(plan.ticket_id), history_text=merged_history
        )
        if resolved:
            plan.ticket_id = resolved
    return plan


def _maybe_draft_reply(
    message: str,
    plan: TicketsPlan,
    ticket: dict[str, Any],
    *,
    lang: str,
) -> None:
    if plan.task_type != TicketsTaskType.ticket_reply:
        return
    if plan.reply_body and not plan.want_draft:
        return
    if plan.want_draft or not (plan.reply_body or "").strip():
        plan.reply_body = draft_ticket_reply(message, ticket, lang=lang)


def _finalize_read_turn(
    db: Session,
    admin: User,
    session,
    plan: TicketsPlan,
    executed: ToolExecutionResult,
    *,
    lang: str,
) -> dict[str, Any]:
    from app.services.admin_client.tickets.tickets_pdf import build_tickets_pdf_export

    reply = compose_tickets_response(executed.processed, plan, lang=lang)
    export_download = None
    if plan.want_pdf and session is not None:
        kind = "detail" if plan.task_type == TicketsTaskType.ticket_detail else "list"
        pdf_note, export_download = build_tickets_pdf_export(
            admin.id,
            session.id,
            export_kind=kind,
            processed=executed.processed,
            lang=lang,
            status_filter=plan.status_filter,
        )
        if export_download is not None:
            reply = pdf_note
        elif pdf_note:
            reply = f"{reply}\n\n{pdf_note}"

    return add_backend_metadata(
        {
            "reply": reply,
            "intent": intent_for_task(plan.task_type),
            "tracking_number": None,
            "shipment": None,
            "export_download": export_download,
            "agent_steps": [
                {"label": t, "status": "done", "detail": None} for t in executed.tools_called
            ],
        },
        tool_used=executed.tools_called[-1] if executed.tools_called else "list_tickets",
        tools_called=executed.tools_called,
        raw_data_received=True,
    )


def run_tickets_pipeline(
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
    from app.services.admin_client.intent_priority import should_route_tickets

    text = (message or "").strip()
    lang = _lang(ui_language, admin)

    merged_history = merge_tickets_history_text(
        db,
        session,
        user_msg_id,
        history_text=history_text,
        conversation_history=conversation_history,
    )

    confirm_turn = _handle_ticket_action_confirm(
        db,
        admin,
        text,
        lang=lang,
        history_text=merged_history,
        conversation_history=conversation_history,
        chat_session_id=getattr(session, "id", None),
        ip_address=ip_address,
    )
    if confirm_turn is not None:
        return confirm_turn

    if not should_route_tickets(text, history_text=merged_history):
        return None

    plan = detect_intent(text, ui_language=lang, history_text=merged_history)
    if plan is None:
        if is_tickets_workspace(text, history_text=merged_history):
            plan = reconcile_tickets_plan(
                text,
                TicketsPlan(
                    task_type=TicketsTaskType.ticket_list,
                    profile=TicketsProfile.LIST,
                    limit=20,
                ),
                history_text=merged_history,
            )
        else:
            return None

    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    plan = _resolve_ticket_target(db, text, plan, merged_history=merged_history, lang=lang)
    if plan is None:
        return None
    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    if plan.task_type in _WRITE_TASKS:
        if not plan.ticket_id:
            return _clarify_turn(
                lang,
                TicketsPlan(
                    task_type=plan.task_type,
                    profile=TicketsProfile.CLARIFY,
                    needs_clarification=True,
                    clarification_question=(
                        "Quel ticket ciblez-vous (#id, TKT-… ou numéro dans la liste) ?"
                        if lang == "fr"
                        else "Which ticket do you mean (#id, TKT-…, or list row number)?"
                    ),
                ),
            )
        if plan.task_type == TicketsTaskType.ticket_reply and not plan.reply_body and not plan.want_draft:
            return _clarify_turn(lang, clarify_missing_reply_body(lang))

        executed = execute_tools(db, plan)
        if not executed.ok:
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"))

        ticket = executed.processed.get("ticket") or {}
        if ticket.get("status") == "closed" and plan.task_type == TicketsTaskType.ticket_reply:
            return _error_turn(lang, detail="ticket_closed")

        _maybe_draft_reply(text, plan, ticket, lang=lang)
        if plan.task_type == TicketsTaskType.ticket_reply and not (plan.reply_body or "").strip():
            return _clarify_turn(lang, clarify_missing_reply_body(lang))

        plan.profile = TicketsProfile.CONFIRM
        reply = compose_tickets_response(executed.processed, plan, lang=lang)
        return add_backend_metadata(
            {
                "reply": reply,
                "intent": intent_for_task(plan.task_type),
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [
                    {"label": t, "status": "done", "detail": "confirm"}
                    for t in executed.tools_called
                ],
            },
            tool_used=executed.tools_called[-1] if executed.tools_called else "get_ticket_detail",
            tools_called=executed.tools_called,
            raw_data_received=True,
            llm_provider="draft_support_reply" if plan.want_draft else None,
        )

    executed = execute_tools(db, plan)
    if not executed.ok:
        return _error_turn(lang, detail=str(executed.error or "fetch_failed"))

    return _finalize_read_turn(db, admin, session, plan, executed, lang=lang)
