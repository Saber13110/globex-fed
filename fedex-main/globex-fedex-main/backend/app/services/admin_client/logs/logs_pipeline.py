"""Pipeline agent Logs admin."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.logs import logs_service, logs_tool
from app.services.admin_client.logs.logs_compose import compose_logs_response
from app.services.admin_client.logs.logs_followup import (
    merge_logs_history_text,
    resolve_log_id_from_context,
)
from app.services.admin_client.logs.logs_intent import (
    TargetLogResolution,
    classify_logs_intent,
    default_clarify_plan,
    resolve_target_log,
    resolve_target_user_for_summary,
)
from app.services.admin_client.logs.logs_pending import (
    is_logs_action_pending,
    is_logs_cancel_message,
    is_logs_confirm_message,
    resolve_pending_log_action,
)
from app.services.admin_client.logs.logs_reconcile import reconcile_logs_plan
from app.services.admin_client.logs.logs_types import (
    LogsPlan,
    LogsProfile,
    LogsTaskType,
    LogsToolError,
)
from app.services.admin_client.logs.logs_workspace import is_logs_workspace

logger = logging.getLogger(__name__)

_WRITE_TASKS = frozenset({LogsTaskType.log_suspend_user})

_FETCH_ERROR_FR = (
    "Je n'ai pas pu récupérer les journaux d'activité en temps réel. "
    "Je ne peux pas donner une réponse fiable."
)
_FETCH_ERROR_EN = "I could not fetch live activity log data. I cannot provide a reliable answer."


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
) -> LogsPlan | None:
    lang = (ui_language or "fr").lower()[:2]
    if lang not in {"fr", "en"}:
        lang = "fr"

    plan = classify_logs_intent(message, history_text=history_text or "", lang=lang)
    if plan.task_type == LogsTaskType.ambiguous and plan.raw_matches == ["user_scoped_defer"]:
        return None
    if plan.needs_clarification:
        return plan
    if plan.task_type == LogsTaskType.ambiguous:
        if is_logs_workspace(message, history_text=history_text or ""):
            return default_clarify_plan(lang)
        return None
    return reconcile_logs_plan(message, plan, history_text=history_text or "")


def execute_tools(db: Session, plan: LogsPlan, *, message: str = "") -> ToolExecutionResult:
    tools_called: list[str] = []
    processed: dict[str, Any] = {}

    try:
        if plan.task_type in {LogsTaskType.log_list, LogsTaskType.log_search}:
            tools_called.append("list_logs")
            data = logs_tool.list_logs(db, plan)
            processed = {**data, "filters": plan}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == LogsTaskType.log_anomalies:
            tools_called.append("analyze_logs")
            analysis = logs_tool.build_anomalies(db, plan, message=message)
            processed = {"analysis": analysis}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == LogsTaskType.log_summary_platform_day:
            tools_called.append("summarize_platform_day")
            summary = logs_tool.build_platform_day_summary(db, plan)
            processed = {"summary": summary}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == LogsTaskType.log_summary_user_day:
            if not plan.user_id:
                return ToolExecutionResult(ok=False, error="user_not_specified", tools_called=tools_called)
            tools_called.append("summarize_user_day")
            summary = logs_tool.build_user_day_summary(db, plan)
            processed = {"summary": summary}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == LogsTaskType.log_detail and plan.log_id:
            tools_called.append("get_log_detail")
            log = logs_tool.get_log_detail(db, int(plan.log_id))
            sid = logs_service.extract_session_id_from_log(log)
            processed = {"log": log, "session_id": sid}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == LogsTaskType.log_open_conversation and plan.log_id:
            tools_called.extend(["get_log_detail", "get_conversation"])
            log = logs_tool.get_log_detail(db, int(plan.log_id))
            sid = logs_service.extract_session_id_from_log(log)
            if not sid:
                return ToolExecutionResult(ok=False, error="no_conversation", tools_called=tools_called)
            from app.services.admin_conversations_service import build_conversation_detail

            detail = build_conversation_detail(db, sid)
            if not detail:
                return ToolExecutionResult(ok=False, error="no_conversation", tools_called=tools_called)
            conv = {
                "session_id": detail.session_id,
                "id": detail.id,
                "title": detail.title,
                "user_name": detail.user_name,
                "user_email": detail.user_email,
                "messages": [
                    {
                        "sender": m.sender,
                        "message_text": m.message_text,
                        "created_at": m.created_at,
                    }
                    for m in (detail.messages or [])
                ],
            }
            processed = {"log": log, "conversation": conv, "session_id": sid}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == LogsTaskType.log_suspend_user and plan.log_id:
            tools_called.extend(["get_log_detail", "get_user"])
            log = logs_tool.get_log_detail(db, int(plan.log_id))
            uid = plan.user_id or logs_service.resolve_user_id_from_log(log)
            if not uid:
                return ToolExecutionResult(ok=False, error="user_not_found", tools_called=tools_called)
            from app.services.admin_client.users import users_tool

            processed = {
                "log": log,
                "user": users_tool.get_user_detail(db, int(uid)),
            }
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        return ToolExecutionResult(ok=False, error="unknown_task", tools_called=tools_called)
    except LogsToolError as exc:
        return ToolExecutionResult(ok=False, error=str(exc), tools_called=tools_called)
    except Exception as exc:  # noqa: BLE001
        logger.exception("logs execute_tools failed: %s", exc)
        return ToolExecutionResult(ok=False, error="fetch_failed", tools_called=tools_called)


def execute_confirmed_action(
    db: Session,
    admin: User,
    pending_action: str,
    user_id: int,
    payload: dict[str, str],
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    if pending_action == "suspend":
        from app.services.admin_client.users import users_service
        from app.services.admin_client.users.users_types import UsersToolError

        try:
            return users_service.suspend_user_account(
                db,
                user_id,
                admin.id,
                reason=payload.get("reason", ""),
                ip_address=ip_address,
            )
        except UsersToolError as exc:
            raise LogsToolError(str(exc)) from exc
    raise LogsToolError("unknown_action")


def intent_for_task(task: LogsTaskType) -> str:
    return {
        LogsTaskType.log_list: "logs_list",
        LogsTaskType.log_search: "logs_search",
        LogsTaskType.log_detail: "logs_detail",
        LogsTaskType.log_summary_user_day: "logs_summary_day",
        LogsTaskType.log_summary_platform_day: "logs_summary_platform_day",
        LogsTaskType.log_anomalies: "logs_anomalies",
        LogsTaskType.log_open_conversation: "logs_conversation",
        LogsTaskType.log_suspend_user: "logs_suspend",
    }.get(task, "logs_query")


def add_backend_metadata(
    response: dict[str, Any],
    *,
    tool_used: str,
    tools_called: list[str],
    raw_data_received: bool,
) -> dict[str, Any]:
    response.update(
        {
            "tool_used": tool_used,
            "tool_called": bool(tools_called),
            "tools_executed": tools_called,
            "data_source": "admin_logs_api",
            "raw_data_received": raw_data_received,
            "confidence": "high" if raw_data_received else "low",
            "llm_provider": None,
            "source": "admin_logs",
        }
    )
    return response


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _error_turn(lang: str, *, detail: str) -> dict[str, Any]:
    from app.services.admin_client.logs.logs_compose import _error_text

    known = {
        "log_not_found", "fetch_failed", "user_not_specified", "user_not_found",
        "no_conversation", "cannot_suspend_admin", "already_suspended",
        "unknown_action", "pending_parse_failed",
    }
    reply = _error_text(detail, lang) if detail in known else (
        _FETCH_ERROR_EN if lang == "en" else _FETCH_ERROR_FR
    )
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "logs_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "logs_service", "status": "error", "detail": detail}],
        },
        tool_used="logs_service",
        tools_called=["logs_service"],
        raw_data_received=False,
    )


def _clarify_turn(lang: str, plan: LogsPlan) -> dict[str, Any]:
    reply = compose_logs_response({}, plan, lang=lang)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "logs_clarify",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "logs_intent", "status": "done", "detail": "clarify"}],
        },
        tool_used="logs_intent",
        tools_called=[],
        raw_data_received=False,
    )


def _handle_action_confirm(
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
    if not is_logs_action_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    if is_logs_cancel_message(message):
        cancel = (
            "Action annulée — aucune modification effectuée."
            if lang == "fr"
            else "Action cancelled — no changes made."
        )
        return add_backend_metadata(
            {
                "reply": cancel,
                "intent": "logs_action_cancelled",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "logs_action", "status": "cancelled", "detail": None}],
            },
            tool_used="logs_action",
            tools_called=[],
            raw_data_received=False,
        )

    if not is_logs_confirm_message(message):
        return None

    pending = resolve_pending_log_action(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    )
    if not pending or not pending.user_id:
        return _error_turn(lang, detail="pending_parse_failed")

    try:
        result = execute_confirmed_action(
            db,
            admin,
            pending.action,
            int(pending.user_id),
            pending.payload,
            ip_address=ip_address,
        )
    except LogsToolError as exc:
        return _error_turn(lang, detail=str(exc))

    from app.services.admin_client.users import users_tool

    processed: dict[str, Any] = {}
    try:
        processed["user"] = users_tool.get_user_detail(db, int(pending.user_id))
    except Exception:
        processed["user"] = {"email": result.get("email")}
    plan = LogsPlan(task_type=LogsTaskType.log_suspend_user, profile=LogsProfile.DONE)
    reply = compose_logs_response(processed, plan, lang=lang, action_result=result)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "logs_suspend_done",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "suspend", "status": "done", "detail": None}],
        },
        tool_used="suspend",
        tools_called=["suspend"],
        raw_data_received=True,
    )


def _apply_log_target(plan: LogsPlan, resolution: TargetLogResolution) -> LogsPlan | None:
    if resolution.needs_clarification:
        plan.needs_clarification = True
        plan.clarification_question = resolution.clarification_question
        plan.profile = LogsProfile.CLARIFY
        return plan
    if resolution.log_id:
        plan.log_id = resolution.log_id
    if resolution.user_id:
        plan.user_id = resolution.user_id
    return plan


def _finalize_read_turn(
    admin: User,
    session,
    plan: LogsPlan,
    executed: ToolExecutionResult,
    *,
    lang: str,
    message: str = "",
) -> dict[str, Any]:
    from app.services.admin_client.logs.logs_export import (
        build_logs_excel_export,
        build_logs_pdf_export,
    )
    from app.services.admin_logs_export_service import parse_log_period_hours

    reply = compose_logs_response(executed.processed, plan, lang=lang)
    export_download = None
    if session is not None and (plan.want_excel or plan.want_pdf):
        combined = f"{message or ''}"
        hours = plan.period_hours or parse_log_period_hours(combined, default=24)
        if plan.want_excel:
            excel_note, export_download = build_logs_excel_export(
                admin.id,
                session.id,
                processed=executed.processed,
                hours=hours,
                lang=lang,
            )
            if export_download is not None:
                reply = excel_note
            elif excel_note:
                reply = f"{reply}\n\n{excel_note}"
        elif plan.want_pdf:
            pdf_note, export_download = build_logs_pdf_export(
                admin.id,
                session.id,
                processed=executed.processed,
                hours=hours,
                lang=lang,
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
            "agent_steps": [{"label": t, "status": "done", "detail": None} for t in executed.tools_called],
        },
        tool_used=executed.tools_called[-1] if executed.tools_called else "list_logs",
        tools_called=executed.tools_called,
        raw_data_received=True,
    )


def run_logs_pipeline(
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
    from app.services.admin_client.intent_priority import should_route_logs

    text = (message or "").strip()
    lang = _lang(ui_language, admin)

    merged_history = merge_logs_history_text(
        db,
        session,
        user_msg_id,
        history_text=history_text,
        conversation_history=conversation_history,
    )

    confirm_turn = _handle_action_confirm(
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

    if not should_route_logs(text, history_text=merged_history):
        return None

    from app.services.admin_client.email.email_patterns import should_defer_logs_to_users

    if should_defer_logs_to_users(text):
        return None

    from app.services.admin_client.logs.logs_export import (
        infer_export_plan_from_message,
        infer_list_plan_from_history,
        is_logs_excel_followup,
        is_logs_pdf_followup,
    )

    direct = infer_export_plan_from_message(text, lang=lang)
    if direct is not None:
        if direct.needs_clarification:
            return _clarify_turn(lang, direct)
        executed = execute_tools(db, direct, message=text)
        if not executed.ok:
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"))
        return _finalize_read_turn(admin, session, direct, executed, lang=lang, message=text)

    if is_logs_excel_followup(text, history_text=merged_history):
        plan = infer_list_plan_from_history(
            merged_history, want_excel=True, message=text
        )
        executed = execute_tools(db, plan, message=text)
        if not executed.ok:
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"))
        return _finalize_read_turn(admin, session, plan, executed, lang=lang, message=text)

    if is_logs_pdf_followup(text, history_text=merged_history):
        plan = infer_list_plan_from_history(
            merged_history, want_pdf=True, message=text
        )
        executed = execute_tools(db, plan, message=text)
        if not executed.ok:
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"))
        return _finalize_read_turn(admin, session, plan, executed, lang=lang, message=text)

    plan = detect_intent(text, ui_language=lang, history_text=merged_history)
    if plan is None:
        if is_logs_workspace(text, history_text=merged_history):
            plan = reconcile_logs_plan(
                text,
                LogsPlan(task_type=LogsTaskType.log_list, profile=LogsProfile.LIST, limit=30),
                history_text=merged_history,
            )
        else:
            return None

    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    if plan.task_type == LogsTaskType.log_summary_user_day:
        res = resolve_target_user_for_summary(db, plan, text, lang=lang)
        plan = _apply_log_target(plan, res)
        if plan and plan.needs_clarification:
            return _clarify_turn(lang, plan)

    if plan.task_type == LogsTaskType.log_summary_platform_day:
        pass

    if plan.task_type in {
        LogsTaskType.log_detail,
        LogsTaskType.log_open_conversation,
        LogsTaskType.log_suspend_user,
    }:
        res = resolve_target_log(db, text, plan, history_text=merged_history, lang=lang)
        plan = _apply_log_target(plan, res)
        if plan and plan.needs_clarification:
            return _clarify_turn(lang, plan)
        if plan.log_id:
            resolved = resolve_log_id_from_context(
                db, int(plan.log_id), history_text=merged_history
            )
            if resolved:
                plan.log_id = resolved
        if plan.task_type == LogsTaskType.log_suspend_user and plan.log_id and not plan.user_id:
            log = logs_service.get_log_detail(db, int(plan.log_id))
            uid = logs_service.resolve_user_id_from_log(log)
            if uid:
                plan.user_id = uid

    if plan.task_type in _WRITE_TASKS:
        executed = execute_tools(db, plan, message=text)
        if not executed.ok:
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"))
        plan.profile = LogsProfile.CONFIRM
        reply = compose_logs_response(executed.processed, plan, lang=lang)
        return add_backend_metadata(
            {
                "reply": reply,
                "intent": intent_for_task(plan.task_type),
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": t, "status": "done", "detail": "confirm"} for t in executed.tools_called],
            },
            tool_used=executed.tools_called[-1] if executed.tools_called else "get_log_detail",
            tools_called=executed.tools_called,
            raw_data_received=True,
        )

    executed = execute_tools(db, plan, message=text)
    if not executed.ok:
        return _error_turn(lang, detail=str(executed.error or "fetch_failed"))

    return _finalize_read_turn(admin, session, plan, executed, lang=lang, message=text)
