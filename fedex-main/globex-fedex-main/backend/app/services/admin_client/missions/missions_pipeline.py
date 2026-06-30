"""Pipeline Mission Control admin — lecture + actions confirmées."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.missions.missions_compose import compose_missions_response, default_clarify
from app.services.admin_client.missions.missions_intent import (
    classify_missions_intent,
    default_clarify_plan,
)
from app.services.admin_client.missions.missions_pending import (
    is_missions_action_pending,
    is_missions_cancel_message,
    is_missions_confirm_message,
    is_missions_delete_phrase,
    resolve_pending_mission_action,
)
from app.services.admin_client.missions.missions_state import (
    validate_cancel,
    validate_delete,
    validate_resume,
    validate_retry,
)
from app.services.admin_client.missions.missions_types import (
    MissionsPlan,
    MissionsProfile,
    MissionsTaskType,
)
from app.services.admin_client.missions.missions_workspace import (
    is_missions_workspace,
    should_exclude_platform_logs,
)
from app.services import agent_mission_service as mission_svc

logger = logging.getLogger(__name__)

_WRITE_CONFIRM_TASKS = frozenset({
    MissionsTaskType.mission_cancel,
    MissionsTaskType.mission_delete,
})

_IMMEDIATE_WRITE_TASKS = frozenset({
    MissionsTaskType.mission_retry,
    MissionsTaskType.mission_resume,
})

_FETCH_ERROR_FR = (
    "Je n'ai pas pu récupérer les missions agent en temps réel. "
    "Je ne peux pas donner une réponse fiable."
)
_FETCH_ERROR_EN = "I could not fetch live agent mission data. I cannot provide a reliable answer."


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
) -> MissionsPlan | None:
    lang = (ui_language or "fr").lower()[:2]
    if lang not in {"fr", "en"}:
        lang = "fr"

    plan = classify_missions_intent(message, history_text=history_text or "", lang=lang)
    if plan.needs_clarification:
        return plan
    if plan.task_type == MissionsTaskType.ambiguous:
        if is_missions_workspace(message, history_text=history_text or ""):
            return default_clarify_plan(lang)
        return None
    return plan


def _mission_row_from_read(mission_read) -> dict[str, Any]:
    data = mission_read.model_dump() if hasattr(mission_read, "model_dump") else dict(mission_read)
    return data


def _resolve_last_failed(db: Session) -> int | None:
    resp = mission_svc.list_missions_filtered(db, status="failed", limit=1)
    items = resp.items
    return int(items[0].id) if items else None


def execute_tools(db: Session, plan: MissionsPlan) -> ToolExecutionResult:
    tools_called: list[str] = []
    processed: dict[str, Any] = {}

    try:
        if plan.task_type == MissionsTaskType.mission_list:
            tools_called.append("list_missions")
            resp = mission_svc.list_missions_filtered(
                db,
                status=plan.status_filter,
                limit=plan.limit,
            )
            processed = {
                "items": [i.model_dump() for i in resp.items],
                "stats": resp.stats,
                "status_filter": plan.status_filter,
            }
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        mission_id = plan.mission_id
        if mission_id is None and plan.status_filter == "failed":
            mission_id = _resolve_last_failed(db)
            plan.mission_id = mission_id

        if mission_id is None:
            return ToolExecutionResult(ok=False, error="mission_not_specified", tools_called=tools_called)

        detail = mission_svc.get_mission(db, int(mission_id))
        if not detail:
            return ToolExecutionResult(ok=False, error="mission_not_found", tools_called=tools_called)

        mission_dict = detail.model_dump()
        processed["mission"] = {
            "id": mission_dict.get("id"),
            "agent_type": mission_dict.get("agent_type"),
            "task_description": mission_dict.get("task_description"),
            "status": mission_dict.get("status"),
        }

        if plan.task_type == MissionsTaskType.mission_results:
            tools_called.append("get_mission_results")
            processed["results"] = mission_dict.get("results") or {}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == MissionsTaskType.mission_logs_summary:
            tools_called.append("summarize_mission_logs")
            processed["logs_summary"] = mission_svc.summarize_mission_logs(db, int(mission_id))
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == MissionsTaskType.mission_retry:
            err = validate_retry(processed["mission"]["status"])
            if err:
                processed["message"] = err
                return ToolExecutionResult(ok=False, error="invalid_state", tools_called=tools_called)
            tools_called.append("run_mission")
            result = mission_svc.run_mission(db, int(mission_id))
            processed["mission"] = _mission_row_from_read(result)
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == MissionsTaskType.mission_resume:
            err = validate_resume(processed["mission"]["status"])
            if err:
                processed["message"] = err
                return ToolExecutionResult(ok=False, error="invalid_state", tools_called=tools_called)
            tools_called.append("resume_mission")
            result = mission_svc.resume_mission(db, int(mission_id))
            processed["mission"] = _mission_row_from_read(result)
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type in _WRITE_CONFIRM_TASKS:
            status = processed["mission"]["status"]
            if plan.task_type == MissionsTaskType.mission_cancel:
                err = validate_cancel(status)
            else:
                err = validate_delete(status)
            if err:
                processed["message"] = err
                return ToolExecutionResult(ok=False, error="invalid_state", tools_called=tools_called)
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        return ToolExecutionResult(ok=False, error="unknown_task", tools_called=tools_called)
    except HTTPException as exc:
        detail = str(exc.detail) if exc.detail else "fetch_failed"
        return ToolExecutionResult(ok=False, error=detail, tools_called=tools_called)
    except Exception as exc:  # noqa: BLE001
        logger.exception("missions execute_tools failed: %s", exc)
        return ToolExecutionResult(ok=False, error="fetch_failed", tools_called=tools_called)


def execute_confirmed_mission_action(
    db: Session,
    action: str,
    mission_id: int,
) -> dict[str, Any]:
    if action == "cancel":
        result = mission_svc.cancel_mission(db, mission_id)
        return _mission_row_from_read(result)
    if action == "delete":
        mission_svc.delete_mission(db, mission_id)
        return {"id": mission_id, "status": "deleted"}
    raise ValueError("unknown_action")


def intent_for_task(task: MissionsTaskType) -> str:
    return {
        MissionsTaskType.mission_list: "missions_list",
        MissionsTaskType.mission_results: "missions_results",
        MissionsTaskType.mission_logs_summary: "missions_logs_summary",
        MissionsTaskType.mission_retry: "missions_retry",
        MissionsTaskType.mission_resume: "missions_resume",
        MissionsTaskType.mission_cancel: "missions_cancel",
        MissionsTaskType.mission_delete: "missions_delete",
    }.get(task, "missions_query")


def add_backend_metadata(
    response: dict[str, Any],
    *,
    tool_used: str,
    tools_called: list[str],
    raw_data_received: bool,
) -> dict[str, Any]:
    conf = "high" if raw_data_received else "low"
    response.update(
        {
            "tool_used": tool_used,
            "tool_called": bool(tools_called),
            "tools_executed": tools_called,
            "data_source": "admin_agent_missions",
            "raw_data_received": raw_data_received,
            "confidence": conf,
            "llm_provider": None,
            "source": "admin_missions",
        }
    )
    return response


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _error_turn(lang: str, *, detail: str, message: str = "") -> dict[str, Any]:
    known = {
        "mission_not_found",
        "fetch_failed",
        "mission_not_specified",
        "invalid_state",
        "unknown_action",
        "pending_parse_failed",
    }
    if detail in known:
        reply = compose_missions_response({}, MissionsPlan(task_type=MissionsTaskType.ambiguous), lang=lang, error_code=detail)
    elif message:
        plan = MissionsPlan(task_type=MissionsTaskType.ambiguous, profile=MissionsProfile.ERROR)
        reply = compose_missions_response({"message": message}, plan, lang=lang)
    else:
        reply = _FETCH_ERROR_EN if lang == "en" else _FETCH_ERROR_FR
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "missions_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "missions_service", "status": "error", "detail": detail}],
        },
        tool_used="missions_service",
        tools_called=["missions_service"],
        raw_data_received=False,
    )


def _clarify_turn(lang: str, plan: MissionsPlan) -> dict[str, Any]:
    reply = compose_missions_response({}, plan, lang=lang)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "missions_clarify",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "missions_intent", "status": "done", "detail": "clarify"}],
        },
        tool_used="missions_intent",
        tools_called=[],
        raw_data_received=False,
    )


def _handle_mission_action_confirm(
    db: Session,
    message: str,
    *,
    lang: str,
    history_text: str | None,
    conversation_history: list[Any] | None,
    chat_session_id: int | None = None,
) -> dict[str, Any] | None:
    if not is_missions_action_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    pending = resolve_pending_mission_action(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    )
    if not pending:
        return None

    if pending.stage == "delete_phrase":
        if is_missions_delete_phrase(message, pending.expected_phrase):
            try:
                execute_confirmed_mission_action(db, "delete", pending.mission_id)
            except HTTPException as exc:
                return _error_turn(lang, detail="invalid_state", message=str(exc.detail))
            except Exception as exc:  # noqa: BLE001
                logger.exception("mission delete failed: %s", exc)
                return _error_turn(lang, detail="fetch_failed")
            plan = MissionsPlan(
                task_type=MissionsTaskType.mission_delete,
                profile=MissionsProfile.DONE,
                mission_id=pending.mission_id,
            )
            reply = compose_missions_response({}, plan, lang=lang, action_result={"id": pending.mission_id})
            return add_backend_metadata(
                {
                    "reply": reply,
                    "intent": "missions_delete_done",
                    "tracking_number": None,
                    "shipment": None,
                    "export_download": None,
                    "agent_steps": [{"label": "delete", "status": "done", "detail": None}],
                },
                tool_used="delete_mission",
                tools_called=["delete_mission"],
                raw_data_received=True,
            )
        if is_missions_cancel_message(message):
            cancel = (
                "Suppression annulée — la mission est inchangée."
                if lang == "fr"
                else "Deletion cancelled — mission unchanged."
            )
            return add_backend_metadata(
                {
                    "reply": cancel,
                    "intent": "missions_action_cancelled",
                    "tracking_number": None,
                    "shipment": None,
                    "export_download": None,
                    "agent_steps": [{"label": "missions_action", "status": "cancelled", "detail": None}],
                },
                tool_used="missions_action",
                tools_called=[],
                raw_data_received=False,
            )
        return None

    if is_missions_cancel_message(message):
        cancel = (
            "Action annulée — aucune modification sur la mission."
            if lang == "fr"
            else "Action cancelled — no mission changes made."
        )
        return add_backend_metadata(
            {
                "reply": cancel,
                "intent": "missions_action_cancelled",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "missions_action", "status": "cancelled", "detail": None}],
            },
            tool_used="missions_action",
            tools_called=[],
            raw_data_received=False,
        )

    if not is_missions_confirm_message(message):
        return None

    try:
        result = execute_confirmed_mission_action(db, pending.action, pending.mission_id)
    except HTTPException as exc:
        return _error_turn(lang, detail="invalid_state", message=str(exc.detail))
    except Exception as exc:  # noqa: BLE001
        logger.exception("mission action failed: %s", exc)
        return _error_turn(lang, detail="fetch_failed")

    task = MissionsTaskType.mission_cancel if pending.action == "cancel" else MissionsTaskType.mission_delete
    plan = MissionsPlan(task_type=task, profile=MissionsProfile.DONE, mission_id=pending.mission_id)
    reply = compose_missions_response({"mission": result}, plan, lang=lang, action_result=result)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": f"missions_{pending.action}_done",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": pending.action, "status": "done", "detail": None}],
        },
        tool_used=pending.action,
        tools_called=[pending.action],
        raw_data_received=True,
    )


def run_missions_pipeline(
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
    from app.services.admin_client.intent_priority import should_route_missions

    text = (message or "").strip()
    lang = _lang(ui_language, admin)
    merged_history = history_text or ""

    confirm_turn = _handle_mission_action_confirm(
        db,
        text,
        lang=lang,
        history_text=merged_history,
        conversation_history=conversation_history,
        chat_session_id=getattr(session, "id", None),
    )
    if confirm_turn is not None:
        return confirm_turn

    if should_exclude_platform_logs(text):
        return None

    if not should_route_missions(text, history_text=merged_history):
        return None

    plan = detect_intent(text, ui_language=lang, history_text=merged_history)
    if plan is None:
        return None

    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    if plan.task_type in _WRITE_CONFIRM_TASKS:
        executed = execute_tools(db, plan)
        if not executed.ok:
            msg = executed.processed.get("message", "")
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"), message=msg)
        plan.profile = (
            MissionsProfile.CONFIRM_DELETE
            if plan.task_type == MissionsTaskType.mission_delete
            else MissionsProfile.CONFIRM
        )
        reply = compose_missions_response(executed.processed, plan, lang=lang)
        return add_backend_metadata(
            {
                "reply": reply,
                "intent": intent_for_task(plan.task_type),
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": plan.task_type.value, "status": "done", "detail": "confirm"}],
            },
            tool_used="get_mission",
            tools_called=["get_mission"],
            raw_data_received=True,
        )

    executed = execute_tools(db, plan)
    if not executed.ok:
        msg = executed.processed.get("message", "")
        return _error_turn(lang, detail=str(executed.error or "fetch_failed"), message=msg)

    if plan.task_type in _IMMEDIATE_WRITE_TASKS:
        plan.profile = MissionsProfile.DONE

    reply = compose_missions_response(executed.processed, plan, lang=lang)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": intent_for_task(plan.task_type),
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [
                {"label": t, "status": "done", "detail": None} for t in executed.tools_called
            ],
        },
        tool_used=executed.tools_called[-1] if executed.tools_called else "missions_intent",
        tools_called=executed.tools_called,
        raw_data_received=True,
    )
