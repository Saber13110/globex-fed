"""Pipeline dashboard admin — outils réels d'abord, LLM reformulation ensuite."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.dashboard.dashboard_answer_engine import (
    format_dashboard_reply,
    intent_for_task,
)
from app.services.admin_client.dashboard.dashboard_intent import (
    classify_dashboard_intent,
    plan_from_router_data,
)
from app.services.admin_client.dashboard.dashboard_narrative import generate_final_answer_with_llm
from app.services.admin_client.dashboard.dashboard_processors import process_dashboard_data
from app.services.admin_client.dashboard.dashboard_reconcile import reconcile_dashboard_plan
from app.services.admin_client.dashboard.dashboard_report import build_delay_report_pdf
from app.services.admin_client.dashboard.dashboard_router import plan_admin_dashboard_task
from app.services.admin_client.dashboard.dashboard_snapshot import (
    DashboardSnapshot,
    collect_dashboard_snapshot,
)
from app.services.admin_client.dashboard.dashboard_tool import DashboardSummaryError
from app.services.admin_client.dashboard.dashboard_types import DashboardPlan, DashboardTaskType

logger = logging.getLogger(__name__)

_FETCH_ERROR_FR = (
    "Je n'ai pas pu récupérer les données admin en temps réel. "
    "Je ne peux pas donner une réponse fiable."
)
_FETCH_ERROR_EN = (
    "I could not fetch live admin dashboard data. "
    "I cannot provide a reliable answer."
)

_MANDATORY_FETCH_TOOL = "get_dashboard_summary"


@dataclass
class ToolExecutionResult:
    ok: bool
    summary: dict[str, Any] = field(default_factory=dict)
    snapshot: DashboardSnapshot | None = None
    tools_called: list[str] = field(default_factory=list)
    error: str | None = None


def detect_intent(
    message: str,
    *,
    ui_language: str,
    history_text: str | None = None,
) -> DashboardPlan | None:
    """Étape 3 — classification intent dashboard."""
    plan = classify_dashboard_intent(message)
    if plan.task_type == DashboardTaskType.ambiguous or plan.needs_router:
        routed = plan_admin_dashboard_task(
            message,
            conversation_history=history_text,
            ui_language=ui_language,
        )
        if routed:
            parsed = plan_from_router_data(routed)
            if parsed is not None:
                return reconcile_dashboard_plan(message, parsed)
        if plan.task_type == DashboardTaskType.ambiguous:
            return None
    return reconcile_dashboard_plan(message, plan)


def select_required_tools(plan: DashboardPlan) -> list[str]:
    """Étape 4 — get_dashboard_summary obligatoire + outils de traitement."""
    _ = plan
    return [
        _MANDATORY_FETCH_TOOL,
        "validate_dashboard_data",
        "detect_dashboard_anomalies",
        "classify_dashboard_priorities",
        "summarize_recent_activity",
    ]


def execute_tools(
    db: Session,
    plan: DashboardPlan,
    *,
    lang: str,
) -> ToolExecutionResult:
    """Étape 5 — collecte réelle PostgreSQL / API admin."""
    try:
        snapshot = collect_dashboard_snapshot(
            db,
            lang=lang,
            period=plan.period,
            role_filter=plan.role,
            status_filter=plan.status,
        )
    except DashboardSummaryError as exc:
        return ToolExecutionResult(ok=False, error=str(exc), tools_called=[_MANDATORY_FETCH_TOOL])

    summary = snapshot.summary or {}
    if not summary:
        return ToolExecutionResult(
            ok=False,
            error="empty_summary",
            snapshot=snapshot,
            tools_called=[_MANDATORY_FETCH_TOOL],
        )
    return ToolExecutionResult(
        ok=True,
        summary=summary,
        snapshot=snapshot,
        tools_called=[_MANDATORY_FETCH_TOOL],
    )


def validate_tool_results(result: ToolExecutionResult) -> dict[str, Any]:
    """Étape 6 — vérifie que l'outil fetch a bien renvoyé des données."""
    if not result.ok or not result.summary:
        return {
            "ok": False,
            "raw_data_received": False,
            "reason": result.error or "fetch_failed",
        }
    return {
        "ok": True,
        "raw_data_received": True,
        "reason": None,
    }


def process_results_with_tools(
    summary: dict[str, Any],
    plan: DashboardPlan,
) -> dict[str, Any]:
    """Étape 7 — analyse déterministe (validation, anomalies, priorités, activité)."""
    return process_dashboard_data(summary, plan)


def _confidence(summary: dict[str, Any], validation: dict[str, Any]) -> str:
    if not validation.get("valid", True):
        return "low"
    dq = summary.get("data_quality") or {}
    if dq.get("has_inconsistency"):
        return "medium"
    if summary.get("anomalies"):
        return "medium"
    return "high"


def add_backend_metadata(
    response: dict[str, Any],
    *,
    summary: dict[str, Any],
    tools_called: list[str],
    validation: dict[str, Any],
    llm_provider: str | None,
) -> dict[str, Any]:
    """Étape 10 — métadonnées imposées par le backend."""
    response.update(
        {
            "tool_used": _MANDATORY_FETCH_TOOL,
            "tool_called": _MANDATORY_FETCH_TOOL in tools_called,
            "tools_executed": tools_called,
            "data_source": "admin_dashboard_api",
            "raw_data_received": bool(summary),
            "confidence": _confidence(summary, validation),
            "llm_provider": llm_provider,
            "source": "admin_dashboard",
        }
    )
    return response


def _error_turn(lang: str, *, detail: str) -> dict[str, Any]:
    return add_backend_metadata(
        {
            "reply": _FETCH_ERROR_FR if lang == "fr" else _FETCH_ERROR_EN,
            "intent": "dashboard_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [
                {"label": _MANDATORY_FETCH_TOOL, "status": "error", "detail": detail},
            ],
        },
        summary={},
        tools_called=[_MANDATORY_FETCH_TOOL],
        validation={"valid": False},
        llm_provider=None,
    )


def _agent_steps(tools_called: list[str], processed_tools: list[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for label in tools_called:
        steps.append({"label": label, "status": "done", "detail": None})
    for label in processed_tools:
        if label not in tools_called:
            steps.append({"label": label, "status": "done", "detail": None})
    return steps


def run_dashboard_pipeline(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
    *,
    history_text: str | None = None,
) -> dict[str, Any] | None:
    """Orchestration complète dashboard admin."""
    from app.services.admin_client.intent_priority import should_route_dashboard

    text = (message or "").strip()
    if not should_route_dashboard(text, history_text=history_text or ""):
        return None

    lang = (ui_language or admin.preferred_language or "fr").lower()[:2]
    if lang not in {"fr", "en"}:
        lang = "fr"

    plan = detect_intent(text, ui_language=lang, history_text=history_text)
    if plan is None:
        return None

    required_tools = select_required_tools(plan)
    executed = execute_tools(db, plan, lang=lang)
    checked = validate_tool_results(executed)

    if not checked["ok"]:
        logger.warning("[admin_dashboard] pipeline fetch échec: %s", checked.get("reason"))
        return _error_turn(lang, detail=str(checked.get("reason") or "fetch_failed"))

    assert executed.snapshot is not None
    processed = process_results_with_tools(executed.summary, plan)
    enriched_summary = processed["summary"]
    executed.snapshot.summary = enriched_summary

    tools_called = list(executed.tools_called) + list(processed.get("tools_run") or [])
    export_download: dict[str, Any] | None = None
    llm_provider: str | None = None

    if plan.task_type == DashboardTaskType.quick_delay_report and plan.include_pdf:
        reply, export_download = build_delay_report_pdf(admin, session, executed.snapshot, plan)
    else:
        reply, llm_provider = generate_final_answer_with_llm(
            text,
            executed.snapshot,
            plan,
            processed_results=processed,
        )

    response = {
        "reply": reply,
        "intent": intent_for_task(plan.task_type),
        "tracking_number": None,
        "shipment": None,
        "export_download": export_download,
        "agent_steps": _agent_steps(executed.tools_called, processed.get("tools_run") or []),
        "dashboard_plan": {
            "task_type": plan.task_type.value,
            "question_type": plan.question_type.value,
            "required_tools": required_tools,
        },
    }
    return add_backend_metadata(
        response,
        summary=enriched_summary,
        tools_called=tools_called,
        validation=processed.get("validation") or {},
        llm_provider=llm_provider,
    )
