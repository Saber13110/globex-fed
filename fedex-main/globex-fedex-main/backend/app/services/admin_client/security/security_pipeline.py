"""Pipeline agent Security IDS admin — Phase 1 lecture seule."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.security import security_tool
from app.services.admin_client.security.security_compose import compose_security_response
from app.services.admin_client.security.security_followup import (
    merge_security_history_text,
    resolve_incident_id_from_context,
)
from app.services.admin_client.security.security_intent import (
    TargetIncidentResolution,
    classify_security_intent,
    default_clarify_plan,
    resolve_target_incident,
)
from app.services.admin_client.security.security_reconcile import reconcile_security_plan
from app.services.admin_client.security.security_types import (
    SecurityPlan,
    SecurityProfile,
    SecurityTaskType,
    SecurityToolError,
)
from app.services.admin_client.security.security_workspace import is_security_workspace

logger = logging.getLogger(__name__)

_FETCH_ERROR_FR = (
    "Je n'ai pas pu récupérer les données sécurité IDS en temps réel. "
    "Je ne peux pas donner une réponse fiable."
)
_FETCH_ERROR_EN = "I could not fetch live security IDS data. I cannot provide a reliable answer."


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
) -> SecurityPlan | None:
    lang = (ui_language or "fr").lower()[:2]
    if lang not in {"fr", "en"}:
        lang = "fr"

    plan = classify_security_intent(message, history_text=history_text or "", lang=lang)
    if plan.task_type == SecurityTaskType.ambiguous and plan.raw_matches == ["logs_anomaly_defer"]:
        return None
    if plan.needs_clarification:
        return plan
    if plan.task_type == SecurityTaskType.ambiguous:
        if is_security_workspace(message, history_text=history_text or ""):
            return default_clarify_plan(lang)
        return None
    return reconcile_security_plan(message, plan, history_text=history_text or "")


def execute_tools(db: Session, plan: SecurityPlan) -> ToolExecutionResult:
    tools_called: list[str] = []
    processed: dict[str, Any] = {}

    try:
        if plan.task_type == SecurityTaskType.security_incident_list:
            tools_called.append("list_incidents")
            data = security_tool.list_incidents(db, plan)
            processed = {**data, "filters": plan}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == SecurityTaskType.security_incident_summary:
            tools_called.append("summarize_incidents")
            summary = security_tool.build_summary(db, plan)
            processed = {"summary": summary}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == SecurityTaskType.security_scan:
            tools_called.append("run_ids_scan")
            scan = security_tool.run_scan(db, plan)
            processed = {"scan": scan}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == SecurityTaskType.security_report:
            tools_called.append("build_security_report")
            report = security_tool.build_report(db, plan)
            processed = {"report": report}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        if plan.task_type == SecurityTaskType.security_incident_detail and plan.incident_id:
            tools_called.append("get_incident_detail")
            incident = security_tool.get_incident_detail(db, int(plan.incident_id))
            processed = {"incident": incident}
            return ToolExecutionResult(ok=True, processed=processed, tools_called=tools_called)

        return ToolExecutionResult(ok=False, error="unknown_task", tools_called=tools_called)
    except SecurityToolError as exc:
        return ToolExecutionResult(ok=False, error=str(exc), tools_called=tools_called)
    except Exception as exc:  # noqa: BLE001
        logger.exception("security execute_tools failed: %s", exc)
        return ToolExecutionResult(ok=False, error="fetch_failed", tools_called=tools_called)


def intent_for_task(task: SecurityTaskType) -> str:
    return {
        SecurityTaskType.security_incident_list: "security_incidents_list",
        SecurityTaskType.security_incident_detail: "security_incident_detail",
        SecurityTaskType.security_incident_summary: "security_incidents_summary",
        SecurityTaskType.security_scan: "security_ids_scan",
        SecurityTaskType.security_report: "security_report",
    }.get(task, "security_query")


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
            "data_source": "admin_security_ids",
            "raw_data_received": raw_data_received,
            "confidence": "high" if raw_data_received else "low",
            "llm_provider": None,
            "source": "admin_security",
        }
    )
    return response


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _error_turn(lang: str, *, detail: str) -> dict[str, Any]:
    from app.services.admin_client.security.security_compose import _error_text

    known = {"incident_not_found", "fetch_failed", "scan_failed", "unknown_task"}
    reply = _error_text(detail, lang) if detail in known else (
        _FETCH_ERROR_EN if lang == "en" else _FETCH_ERROR_FR
    )
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "security_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "security_service", "status": "error", "detail": detail}],
        },
        tool_used="security_service",
        tools_called=["security_service"],
        raw_data_received=False,
    )


def _clarify_turn(lang: str, plan: SecurityPlan) -> dict[str, Any]:
    reply = compose_security_response({}, plan, lang=lang)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "security_clarify",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "security_intent", "status": "done", "detail": "clarify"}],
        },
        tool_used="security_intent",
        tools_called=[],
        raw_data_received=False,
    )


def _apply_incident_target(plan: SecurityPlan, resolution: TargetIncidentResolution) -> SecurityPlan | None:
    if resolution.needs_clarification:
        plan.needs_clarification = True
        plan.clarification_question = resolution.clarification_question
        plan.profile = SecurityProfile.CLARIFY
        return plan
    if resolution.incident_id:
        plan.incident_id = resolution.incident_id
    return plan


def _finalize_read_turn(
    admin: User,
    session,
    plan: SecurityPlan,
    executed: ToolExecutionResult,
    *,
    lang: str,
) -> dict[str, Any]:
    from app.services.admin_client.security.security_pdf import build_security_pdf_export

    reply = compose_security_response(executed.processed, plan, lang=lang)
    export_download = None
    if plan.want_pdf and session is not None:
        pdf_note, export_download = build_security_pdf_export(
            admin.id,
            session.id,
            plan=plan,
            processed=executed.processed,
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
        tool_used=executed.tools_called[-1] if executed.tools_called else "list_incidents",
        tools_called=executed.tools_called,
        raw_data_received=True,
    )


def run_security_pipeline(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
) -> dict[str, Any] | None:
    from app.services.admin_client.intent_priority import should_route_security

    text = (message or "").strip()
    lang = _lang(ui_language, admin)

    merged_history = merge_security_history_text(
        db,
        session,
        user_msg_id,
        history_text=history_text,
        conversation_history=conversation_history,
    )

    if not should_route_security(text, history_text=merged_history):
        return None

    from app.services.admin_client.security.security_pdf import (
        infer_pdf_plan,
        is_security_pdf_followup,
    )

    if is_security_pdf_followup(text, history_text=merged_history):
        plan = infer_pdf_plan(text, history_text=merged_history)
        if plan.task_type == SecurityTaskType.security_incident_detail:
            res = resolve_target_incident(db, text, plan, history_text=merged_history, lang=lang)
            plan = _apply_incident_target(plan, res)
        executed = execute_tools(db, plan)
        if not executed.ok:
            return _error_turn(lang, detail=str(executed.error or "fetch_failed"))
        return _finalize_read_turn(admin, session, plan, executed, lang=lang)

    plan = detect_intent(text, ui_language=lang, history_text=merged_history)
    if plan is None:
        return None

    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    if plan.task_type == SecurityTaskType.security_incident_detail:
        res = resolve_target_incident(db, text, plan, history_text=merged_history, lang=lang)
        plan = _apply_incident_target(plan, res)
        if plan and plan.needs_clarification:
            return _clarify_turn(lang, plan)
        if plan.incident_id:
            resolved = resolve_incident_id_from_context(
                db, int(plan.incident_id), history_text=merged_history
            )
            if resolved:
                plan.incident_id = resolved

    executed = execute_tools(db, plan)
    if not executed.ok:
        return _error_turn(lang, detail=str(executed.error or "fetch_failed"))

    return _finalize_read_turn(admin, session, plan, executed, lang=lang)
