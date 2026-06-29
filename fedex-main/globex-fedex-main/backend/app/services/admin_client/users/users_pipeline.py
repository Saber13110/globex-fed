"""Pipeline agent Utilisateurs admin — outils réels, réponses déterministes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.users.users_compose import compose_users_response
from app.services.admin_client.users.users_intent import (
    TargetUserResolution,
    classify_users_intent,
    clarify_plan_from_router,
    default_clarify_plan,
    plan_from_router_data,
    resolve_target_user,
)
from app.services.admin_client.users.users_pending import (
    is_users_action_pending,
    is_users_cancel_message,
    is_users_confirm_message,
    resolve_pending_user_action,
)
from app.services.admin_client.users.users_reconcile import reconcile_users_plan
from app.services.admin_client.users.users_router import plan_admin_users_task
from app.services.admin_client.users.users_types import UsersPlan, UsersProfile, UsersTaskType, UsersToolError
from app.services.admin_client.users.users_workspace import is_users_workspace
from app.services.admin_client.users import users_service, users_tool

logger = logging.getLogger(__name__)

_WRITE_TASKS = frozenset({
    UsersTaskType.user_suspend,
    UsersTaskType.user_reactivate,
    UsersTaskType.user_delete,
    UsersTaskType.user_update_name,
    UsersTaskType.user_reset_password,
})

_FETCH_ERROR_FR = (
    "Je n'ai pas pu récupérer les données utilisateurs en temps réel. "
    "Je ne peux pas donner une réponse fiable."
)
_FETCH_ERROR_EN = "I could not fetch live user data. I cannot provide a reliable answer."


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
) -> UsersPlan | None:
    lang = (ui_language or "fr").lower()[:2]
    if lang not in {"fr", "en"}:
        lang = "fr"

    plan = classify_users_intent(message, history_text=history_text or "")
    if plan.needs_clarification:
        return plan

    if plan.task_type == UsersTaskType.ambiguous or plan.needs_router:
        routed = plan_admin_users_task(
            message,
            conversation_history=history_text,
            ui_language=lang,
        )
        if routed:
            if routed.get("needs_clarification") and routed.get("clarification_question"):
                return clarify_plan_from_router(routed)
            parsed = plan_from_router_data(routed)
            if parsed is not None:
                return reconcile_users_plan(message, parsed, history_text=history_text or "")
        if plan.task_type == UsersTaskType.ambiguous:
            if is_users_workspace(message, history_text=history_text or ""):
                return default_clarify_plan(lang)
            return None

    if plan.task_type == UsersTaskType.ambiguous:
        return None

    return reconcile_users_plan(message, plan, history_text=history_text or "")


def _apply_target(plan: UsersPlan, resolution: TargetUserResolution) -> UsersPlan | None:
    if resolution.needs_clarification:
        plan.needs_clarification = True
        plan.clarification_question = resolution.clarification_question
        plan.clarification_candidates = resolution.candidates or []
        plan.profile = UsersProfile.CLARIFY
        return plan
    if resolution.user_id:
        plan.user_id = resolution.user_id
    return plan


def execute_tools(db: Session, plan: UsersPlan, *, lang: str = "fr") -> ToolExecutionResult:
    tools_called: list[str] = []
    processed: dict[str, Any] = {}

    try:
        if plan.task_type == UsersTaskType.user_list:
            tools_called.append("list_users")
            users = users_tool.list_users(db, plan)
            processed = {
                "users": users,
                "filters": {
                    "role": plan.role_filter,
                    "status": plan.status_filter,
                    "search": plan.search_query,
                    "sort": plan.sort_by,
                    "list_variant": plan.list_variant,
                },
            }
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if not plan.user_id:
            return ToolExecutionResult(ok=False, error="user_not_specified", tools_called=tools_called)

        uid = int(plan.user_id)
        if plan.task_type == UsersTaskType.user_detail:
            tools_called.append("get_user_detail")
            processed["user"] = users_tool.get_user_detail(db, uid)
        elif plan.task_type == UsersTaskType.user_logs:
            tools_called.extend(["get_user_detail", "get_user_logs"])
            processed["user"] = users_tool.get_user_detail(db, uid)
            logs_resp = users_tool.get_user_logs(db, uid)
            processed["logs"] = logs_resp.get("items") or []
            processed["logs_total"] = logs_resp.get("total", 0)
        elif plan.task_type == UsersTaskType.user_permissions:
            tools_called.append("get_user_permissions")
            processed["permissions"] = users_tool.get_user_permissions(db, uid)
        elif plan.task_type in _WRITE_TASKS:
            tools_called.append("get_user_detail")
            processed["user"] = users_tool.get_user_detail(db, uid)
        else:
            return ToolExecutionResult(ok=False, error="unknown_task", tools_called=tools_called)

        return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)
    except UsersToolError as exc:
        return ToolExecutionResult(ok=False, error=str(exc), tools_called=tools_called)
    except Exception as exc:  # noqa: BLE001
        logger.exception("users execute_tools failed: %s", exc)
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
        return users_service.suspend_user_account(
            db, user_id, admin.id, reason=payload.get("reason", ""), ip_address=ip_address
        )
    if pending_action == "reactivate":
        return users_service.reactivate_user_account(db, user_id, admin.id, ip_address=ip_address)
    if pending_action == "delete":
        return users_service.delete_user_account(db, user_id, admin.id, ip_address=ip_address)
    if pending_action == "update_name":
        return users_service.update_user_name(
            db, user_id, admin.id, payload.get("new_name", ""), ip_address=ip_address
        ).model_dump()
    if pending_action in {"reset_password", "reset"}:
        return users_service.reset_user_password(db, user_id, admin.id, ip_address=ip_address)
    raise UsersToolError("unknown_action")


def _task_from_pending_action(action: str) -> UsersTaskType:
    mapping = {
        "suspend": UsersTaskType.user_suspend,
        "reactivate": UsersTaskType.user_reactivate,
        "delete": UsersTaskType.user_delete,
        "update_name": UsersTaskType.user_update_name,
        "reset_password": UsersTaskType.user_reset_password,
        "reset": UsersTaskType.user_reset_password,
    }
    return mapping.get(action, UsersTaskType.ambiguous)


def intent_for_task(task: UsersTaskType) -> str:
    return {
        UsersTaskType.user_list: "users_list",
        UsersTaskType.user_detail: "users_detail",
        UsersTaskType.user_logs: "users_logs",
        UsersTaskType.user_permissions: "users_permissions",
        UsersTaskType.user_suspend: "users_suspend",
        UsersTaskType.user_reactivate: "users_reactivate",
        UsersTaskType.user_delete: "users_delete",
        UsersTaskType.user_update_name: "users_rename",
        UsersTaskType.user_reset_password: "users_reset_password",
    }.get(task, "users_query")


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
            "data_source": "admin_users_api",
            "raw_data_received": raw_data_received,
            "confidence": conf,
            "llm_provider": llm_provider,
            "source": "admin_users",
        }
    )
    return response


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _error_turn(lang: str, *, detail: str) -> dict[str, Any]:
    from app.services.admin_client.users.users_compose import _error_text

    return add_backend_metadata(
        {
            "reply": _error_text(detail, lang) if detail in {
                "user_not_found", "cannot_suspend_admin", "already_suspended",
                "reactivate_failed", "cannot_delete_self", "cannot_delete_last_admin",
                "invalid_name", "smtp_not_configured",
            } or detail.startswith("email_send_failed:") else (
                _FETCH_ERROR_EN if lang == "en" else _FETCH_ERROR_FR
            ),
            "intent": "users_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "users_service", "status": "error", "detail": detail}],
        },
        tool_used="users_service",
        tools_called=["users_service"],
        raw_data_received=False,
    )


def _clarify_turn(lang: str, plan: UsersPlan) -> dict[str, Any]:
    reply = compose_users_response({}, plan, lang=lang)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "users_clarify",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "users_router", "status": "done", "detail": "clarify"}],
        },
        tool_used="users_router",
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
    from app.services.admin_client.pending_resolver import is_latest_pending_kind

    if not is_latest_pending_kind(
        "users",
        db=db,
        chat_session_id=chat_session_id,
        conversation_history=conversation_history,
    ):
        return None

    if not is_users_action_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    if is_users_cancel_message(message):
        cancel = (
            "Action annulée — aucune modification effectuée."
            if lang == "fr"
            else "Action cancelled — no changes made."
        )
        return add_backend_metadata(
            {
                "reply": cancel,
                "intent": "users_action_cancelled",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "users_action", "status": "cancelled", "detail": None}],
            },
            tool_used="users_action",
            tools_called=[],
            raw_data_received=False,
        )

    if not is_users_confirm_message(message):
        return None

    pending = resolve_pending_user_action(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    )
    if not pending:
        return _error_turn(lang, detail="pending_parse_failed")

    try:
        result = execute_confirmed_action(
            db,
            admin,
            pending.action,
            pending.user_id,
            pending.payload,
            ip_address=ip_address,
        )
    except UsersToolError as exc:
        return _error_turn(lang, detail=str(exc))

    task = _task_from_pending_action(pending.action)
    plan = UsersPlan(task_type=task, profile=UsersProfile.DONE, user_id=pending.user_id)
    processed: dict[str, Any] = {}
    try:
        processed["user"] = users_tool.get_user_detail(db, pending.user_id)
    except UsersToolError:
        processed["user"] = {"email": result.get("email")}
    reply = compose_users_response(processed, plan, lang=lang, action_result=result)

    from app.services.admin_client.email.email_action_hooks import (
        apply_post_action_email_hook,
        build_admin_note_for_users_action,
        scenario_for_users_task,
        should_offer_email_after_users_action,
    )

    scenario = scenario_for_users_task(task)
    if scenario and (
        should_offer_email_after_users_action(task) or pending.payload.get("notify_email") == "true"
    ):
        user_row = processed.get("user") or {}
        recipient_email = str(user_row.get("email") or result.get("email") or "")
        admin_note = build_admin_note_for_users_action(
            task,
            reason=pending.payload.get("reason", ""),
            lang=lang,
        )
        notify_inline = pending.payload.get("notify_email") == "true"
        hook_result = apply_post_action_email_hook(
            db,
            admin,
            reply,
            user_id=pending.user_id,
            scenario=scenario,
            admin_note=admin_note,
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
            "intent": f"users_{pending.action}_done",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": pending.action, "status": "done", "detail": None}],
        },
        tool_used=pending.action,
        tools_called=[pending.action],
        raw_data_received=True,
    )


def _maybe_router_plan(
    message: str,
    plan: UsersPlan,
    *,
    history_text: str,
    lang: str,
) -> UsersPlan | None:
    if plan.task_type != UsersTaskType.ambiguous and not plan.needs_router:
        return None
    routed = plan_admin_users_task(
        message,
        conversation_history=history_text,
        ui_language=lang,
    )
    if not routed:
        return None
    if routed.get("needs_clarification") and routed.get("clarification_question"):
        return clarify_plan_from_router(routed)
    parsed = plan_from_router_data(routed)
    if parsed is not None:
        return reconcile_users_plan(message, parsed, history_text=history_text)
    return None


def _finalize_read_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    plan: UsersPlan,
    executed: ToolExecutionResult,
    *,
    lang: str,
) -> dict[str, Any]:
    from app.services.admin_client.users.users_narrative import generate_users_answer_with_llm
    from app.services.admin_client.users.users_pdf import build_users_pdf_export

    llm_provider: str | None = None
    if plan.profile in {UsersProfile.LIST, UsersProfile.LOGS}:
        reply = compose_users_response(executed.processed, plan, lang=lang, include_footer=False)
    else:
        reply, llm_provider = generate_users_answer_with_llm(
            message, executed.processed, plan, lang=lang
        )
    export_download = None
    if plan.want_pdf and session is not None:
        kind = "logs" if plan.task_type == UsersTaskType.user_logs else "list"
        pdf_note, export_download = build_users_pdf_export(
            admin.id,
            session.id,
            export_kind=kind,
            processed=executed.processed,
            lang=lang,
            status_filter=plan.status_filter,
            list_variant=plan.list_variant,
            sort_by=plan.sort_by,
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
        tool_used=executed.tools_called[-1] if executed.tools_called else "list_users",
        tools_called=executed.tools_called,
        raw_data_received=True,
        llm_provider=llm_provider,
    )


def run_users_pipeline(
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
    from app.services.admin_client.intent_priority import should_route_users

    text = (message or "").strip()
    lang = _lang(ui_language, admin)

    confirm_turn = _handle_action_confirm(
        db,
        admin,
        text,
        lang=lang,
        history_text=history_text,
        conversation_history=conversation_history,
        chat_session_id=getattr(session, "id", None),
        ip_address=ip_address,
    )
    if confirm_turn is not None:
        return confirm_turn

    if not should_route_users(text, history_text=history_text or ""):
        return None

    plan = detect_intent(text, ui_language=lang, history_text=history_text)
    if plan is not None and (plan.task_type == UsersTaskType.ambiguous or plan.needs_router):
        routed_plan = _maybe_router_plan(text, plan, history_text=history_text or "", lang=lang)
        if routed_plan is not None:
            plan = routed_plan
    if plan is None:
        if is_users_workspace(text, history_text=history_text or ""):
            plan = reconcile_users_plan(
                text,
                UsersPlan(task_type=UsersTaskType.user_list, profile=UsersProfile.LIST, limit=15),
                history_text=history_text or "",
            )
        else:
            return None

    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    if plan.task_type != UsersTaskType.user_list:
        resolution = resolve_target_user(db, text, plan, history_text=history_text or "", lang=lang)
        clarified = _apply_target(plan, resolution)
        if clarified and clarified.needs_clarification:
            return _clarify_turn(lang, clarified)

    if plan.task_type in _WRITE_TASKS:
        if not plan.user_id:
            return _clarify_turn(
                lang,
                UsersPlan(
                    task_type=plan.task_type,
                    profile=UsersProfile.CLARIFY,
                    needs_clarification=True,
                    clarification_question=(
                        "Quel utilisateur ciblez-vous (e-mail, #id ou numéro dans la liste) ?"
                        if lang == "fr"
                        else "Which user do you mean (email, #id, or list number)?"
                    ),
                ),
            )
        executed = execute_tools(db, plan, lang=lang)
        if not executed.ok:
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"))
        plan.profile = UsersProfile.CONFIRM
        reply = compose_users_response(executed.processed, plan, lang=lang)
        return add_backend_metadata(
            {
                "reply": reply,
                "intent": intent_for_task(plan.task_type),
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": t, "status": "done", "detail": "confirm"} for t in executed.tools_called],
            },
            tool_used=executed.tools_called[-1] if executed.tools_called else "users_service",
            tools_called=executed.tools_called,
            raw_data_received=True,
        )

    executed = execute_tools(db, plan, lang=lang)
    if not executed.ok:
        return _error_turn(lang, detail=str(executed.error or "fetch_failed"))

    return _finalize_read_turn(db, admin, session, text, plan, executed, lang=lang)
