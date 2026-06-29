"""Pipeline agent Reports admin — outils réels, LLM reformulation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.reports.reports_center_snapshot import resolve_target_run
from app.services.admin_client.reports.reports_compose import compose_reports_response
from app.services.admin_client.reports.reports_intent import classify_reports_intent
from app.services.admin_client.reports.reports_narrative import generate_final_answer_with_llm
from app.services.admin_client.reports.reports_processors import process_report_data, resolve_recipients
from app.services.admin_client.reports.reports_share_pending import (
    _last_assistant_from_history,
    is_share_cancel_message,
    is_share_confirm_message,
    is_share_pending,
    parse_pending_share,
)
from app.services.admin_client.reports.reports_types import (
    ReportsPlan,
    ReportsProfile,
    ReportsTaskType,
    ReportsToolError,
)

logger = logging.getLogger(__name__)

_FETCH_ERROR_FR = (
    "Je n'ai pas pu récupérer les données admin en temps réel. "
    "Je ne peux pas donner une réponse fiable."
)
_FETCH_ERROR_EN = (
    "I could not fetch live admin dashboard data. "
    "I cannot provide a reliable answer."
)
_ERROR_DETAIL_FR: dict[str, str] = {
    "file_missing": (
        "L'export est enregistré en base mais le fichier n'est plus disponible sur le disque. "
        "Régénérez-le depuis le Centre de rapports."
    ),
    "run_not_found": "Aucun export correspondant trouvé dans le Centre de rapports.",
    "run_not_completed": "Cet export n'est pas encore terminé ou a échoué.",
    "preview_failed": "Impossible de lire le contenu de cet export.",
    "share_failed": "Impossible d'envoyer le rapport — fichier ou SMTP indisponible.",
    "format_not_found": "Aucun export récent ne correspond au format demandé.",
}
_ERROR_DETAIL_EN: dict[str, str] = {
    "file_missing": (
        "The export exists in the database but the file is no longer on disk. "
        "Regenerate it from the Reports Center."
    ),
    "run_not_found": "No matching export found in the Reports Center.",
    "run_not_completed": "This export is not finished or has failed.",
    "preview_failed": "Could not read this export's contents.",
    "share_failed": "Could not send the report — file or SMTP unavailable.",
    "format_not_found": "No recent export matches the requested format.",
}


@dataclass
class ToolExecutionResult:
    ok: bool
    runs: list[dict[str, Any]] = field(default_factory=list)
    run: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    tools_called: list[str] = field(default_factory=list)
    error: str | None = None


def detect_intent(
    message: str,
    *,
    ui_language: str = "fr",
    history_text: str | None = None,
) -> ReportsPlan | None:
    from app.services.admin_client.reports.reports_intent import (
        clarify_plan_from_router,
        classify_reports_intent,
        default_clarify_plan,
        plan_from_router_data,
    )
    from app.services.admin_client.reports.reports_reconcile import reconcile_reports_plan
    from app.services.admin_client.reports.reports_router import plan_admin_reports_task
    from app.services.admin_client.reports.reports_workspace import is_reports_workspace

    lang = (ui_language or "fr").lower()[:2]
    if lang not in {"fr", "en"}:
        lang = "fr"

    plan = classify_reports_intent(message, history_text=history_text or "")
    if plan.needs_clarification:
        return plan

    if plan.task_type == ReportsTaskType.ambiguous or plan.needs_router:
        routed = plan_admin_reports_task(
            message,
            conversation_history=history_text,
            ui_language=lang,
        )
        if routed:
            if routed.get("needs_clarification") and routed.get("clarification_question"):
                return clarify_plan_from_router(routed)
            parsed = plan_from_router_data(routed)
            if parsed is not None:
                return reconcile_reports_plan(message, parsed, history_text=history_text or "")
        if plan.task_type == ReportsTaskType.ambiguous:
            if is_reports_workspace(message, history_text=history_text or ""):
                return default_clarify_plan(lang)
            return None

    if plan.task_type == ReportsTaskType.ambiguous:
        return None

    return reconcile_reports_plan(message, plan, history_text=history_text or "")


def select_required_tools(plan: ReportsPlan) -> list[str]:
    tools = ["get_reports_center_snapshot", "validate_report_data"]
    if plan.task_type in (
        ReportsTaskType.report_preview,
        ReportsTaskType.report_redownload,
        ReportsTaskType.report_share,
    ):
        tools.extend(["resolve_target_run", "get_report_run"])
    if plan.task_type == ReportsTaskType.report_preview:
        tools.append("preview_report")
    if plan.task_type == ReportsTaskType.report_share:
        tools.append("search_users")
    return tools


def execute_tools(db: Session, plan: ReportsPlan) -> ToolExecutionResult:
    from app.services.admin_client.reports import reports_tool

    tools_called = ["get_reports_center_snapshot"]
    search = plan.search_filter
    try:
        snapshot = reports_tool.fetch_reports_center(
            db,
            fmt=plan.format_filter,
            search=search,
            slug=plan.slug_hint,
            limit=plan.limit,
        )
    except ReportsToolError as exc:
        return ToolExecutionResult(ok=False, error=str(exc), tools_called=tools_called)

    runs = list(snapshot.get("recent_runs") or [])
    run: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None

    if plan.task_type in (
        ReportsTaskType.report_preview,
        ReportsTaskType.report_redownload,
        ReportsTaskType.report_share,
    ):
        require_file = plan.task_type == ReportsTaskType.report_redownload
        if plan.task_type == ReportsTaskType.report_share:
            require_file = False

        try:
            run = resolve_target_run(db, plan, snapshot, require_file=require_file)
            tools_called.extend(["resolve_target_run", "get_report_run"])
        except ReportsToolError as exc:
            err = str(exc)
            if plan.task_type == ReportsTaskType.report_preview and (
                err == "file_missing" or err.startswith("format_not_found:")
            ):
                try:
                    run = resolve_target_run(db, plan, snapshot, require_file=False)
                    tools_called.extend(["resolve_target_run", "get_report_run"])
                except ReportsToolError as exc2:
                    return ToolExecutionResult(
                        ok=False, runs=runs, snapshot=snapshot, error=str(exc2), tools_called=tools_called
                    )
            elif err.startswith("format_not_found:") and runs:
                return ToolExecutionResult(
                    ok=False, runs=runs, snapshot=snapshot, error=err, tools_called=tools_called
                )
            else:
                return ToolExecutionResult(
                    ok=False, runs=runs, snapshot=snapshot, error=err, tools_called=tools_called
                )

        if plan.task_type == ReportsTaskType.report_preview and run:
            file_ok = (snapshot.get("file_available") or {}).get(int(run["id"]), False)
            if file_ok:
                try:
                    preview = reports_tool.preview_report(db, int(run["id"]))
                    tools_called.append("preview_report")
                except ReportsToolError:
                    preview = None
            else:
                preview = None

    if plan.task_type == ReportsTaskType.report_share:
        tools_called.append("search_users")

    return ToolExecutionResult(
        ok=True, runs=runs, run=run, preview=preview, snapshot=snapshot, tools_called=tools_called
    )


def validate_tool_results(result: ToolExecutionResult, plan: ReportsPlan) -> dict[str, Any]:
    if not result.ok:
        return {"ok": False, "raw_data_received": False, "reason": result.error}
    if plan.task_type == ReportsTaskType.report_list_recent:
        has_data = bool(result.runs) or bool((result.snapshot or {}).get("catalog"))
        return {"ok": has_data, "raw_data_received": has_data, "reason": None}
    if not result.run:
        return {"ok": False, "raw_data_received": False, "reason": "run_not_found"}
    if plan.task_type == ReportsTaskType.report_share:
        return {"ok": True, "raw_data_received": True, "reason": None}
    file_ok = (result.snapshot.get("file_available") or {}).get(int(result.run["id"]), False)
    if plan.task_type == ReportsTaskType.report_preview:
        return {"ok": True, "raw_data_received": True, "reason": None}
    if plan.task_type == ReportsTaskType.report_redownload:
        if not file_ok:
            return {"ok": False, "raw_data_received": False, "reason": "file_missing"}
    return {"ok": True, "raw_data_received": True, "reason": None}


def process_results_with_tools(
    *,
    plan: ReportsPlan,
    executed: ToolExecutionResult,
    message: str,
    db: Session,
) -> dict[str, Any]:
    users: list[dict[str, Any]] = []
    if plan.task_type == ReportsTaskType.report_share:
        q = plan.recipient_query or message
        from app.services.admin_client.reports import reports_tool

        users = reports_tool.search_users_for_reports(db, q)
    recipients = resolve_recipients(message, users, explicit_query=plan.recipient_query)
    processed = process_report_data(
        plan=plan,
        runs=executed.runs,
        run=executed.run,
        preview=executed.preview,
        recipients=recipients,
    )
    processed["catalog"] = executed.snapshot.get("catalog") or []
    processed["file_available"] = executed.snapshot.get("file_available") or {}
    processed["filters"] = executed.snapshot.get("filters") or {}
    return processed


def intent_for_task(task: ReportsTaskType) -> str:
    return {
        ReportsTaskType.report_preview: "reports_preview",
        ReportsTaskType.report_list_recent: "reports_list",
        ReportsTaskType.report_redownload: "reports_download",
        ReportsTaskType.report_share: "reports_share",
    }.get(task, "reports_query")


def _primary_tool(plan: ReportsPlan, *, share_executed: bool = False) -> str:
    if share_executed:
        return "share_report_email"
    if plan.task_type == ReportsTaskType.report_preview:
        return "preview_report"
    if plan.task_type == ReportsTaskType.report_redownload:
        return "get_report_run"
    return "get_reports_center_snapshot"


def add_backend_metadata(
    response: dict[str, Any],
    *,
    tool_used: str,
    tools_called: list[str],
    raw_data_received: bool,
    validation: dict[str, Any],
    llm_provider: str | None,
) -> dict[str, Any]:
    conf = "high"
    if not raw_data_received:
        conf = "low"
    elif not validation.get("valid", True):
        conf = "medium"
    response.update(
        {
            "tool_used": tool_used,
            "tool_called": bool(tools_called),
            "tools_executed": tools_called,
            "data_source": "admin_reports_api",
            "raw_data_received": raw_data_received,
            "confidence": conf,
            "llm_provider": llm_provider,
            "source": "admin_reports",
        }
    )
    return response


def _error_message(lang: str, detail: str) -> str:
    catalog = _ERROR_DETAIL_EN if lang == "en" else _ERROR_DETAIL_FR
    if detail in catalog:
        return catalog[detail]
    if detail.startswith("format_not_found:"):
        fmt = detail.split(":", 1)[-1]
        if lang == "en":
            return f"No recent **{fmt}** export found."
        return f"Aucun export récent au format **{fmt}** trouvé."
    return _FETCH_ERROR_EN if lang == "en" else _FETCH_ERROR_FR


_FILE_MISSING_ERRORS = frozenset({"file_missing", "preview_failed"})


def _should_partial_file_list(executed: ToolExecutionResult, reason: str | None = None) -> bool:
    err = (reason or executed.error or "").strip()
    return bool(executed.runs) and err in _FILE_MISSING_ERRORS


def _partial_file_response(
    lang: str,
    *,
    executed: ToolExecutionResult,
    message: str,
    db: Session,
) -> dict[str, Any]:
    list_plan = ReportsPlan(
        task_type=ReportsTaskType.report_list_recent,
        profile=ReportsProfile.LIST,
    )
    processed = process_results_with_tools(plan=list_plan, executed=executed, message=message, db=db)
    return _partial_file_missing_turn(
        lang, processed=processed, tools_called=list(executed.tools_called)
    )


def _partial_file_missing_turn(
    lang: str,
    *,
    processed: dict[str, Any],
    tools_called: list[str],
) -> dict[str, Any]:
    note = _error_message(lang, "file_missing")
    list_plan = ReportsPlan(
        task_type=ReportsTaskType.report_list_recent,
        profile=ReportsProfile.LIST,
    )
    reply = compose_reports_response(processed, list_plan, lang=lang) + "\n\n---\n\n" + note
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "reports_list",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": t, "status": "done", "detail": None} for t in tools_called],
        },
        tool_used="get_reports_center_snapshot",
        tools_called=tools_called,
        raw_data_received=True,
        validation={"valid": True, "partial": True, "reason": "file_missing"},
        llm_provider=None,
    )


def _clarify_turn(lang: str, plan: ReportsPlan) -> dict[str, Any]:
    reply = compose_reports_response({}, plan, lang=lang)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "reports_clarify",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "reports_router", "status": "done", "detail": "clarify"}],
        },
        tool_used="reports_router",
        tools_called=[],
        raw_data_received=False,
        validation={"valid": True, "clarification": True},
        llm_provider=None,
    )


def _error_turn(lang: str, *, detail: str) -> dict[str, Any]:
    return add_backend_metadata(
        {
            "reply": _error_message(lang, detail),
            "intent": "reports_error",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "get_reports_center_snapshot", "status": "error", "detail": detail}],
        },
        tool_used="get_reports_center_snapshot",
        tools_called=["get_reports_center_snapshot"],
        raw_data_received=False,
        validation={"valid": False},
        llm_provider=None,
    )


def _build_export_download(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None
    return {
        "url": run.get("download_url"),
        "filename": f"report_{run.get('id')}_{run.get('slug', 'export')}.{run.get('format', 'xlsx')}",
        "format": run.get("format"),
        "run_id": run.get("id"),
    }


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en"} else "fr"


def _handle_share_confirm(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    history_text: str | None,
    conversation_history: list[Any] | None,
    chat_session_id: int | None = None,
) -> dict[str, Any] | None:
    if not is_share_pending(
        history_text=history_text,
        conversation_history=conversation_history,
        db=db,
        chat_session_id=chat_session_id,
    ):
        return None

    if is_share_cancel_message(message):
        cancel = (
            "Partage annulé — aucun e-mail envoyé."
            if lang == "fr"
            else "Sharing cancelled — no email sent."
        )
        return add_backend_metadata(
            {
                "reply": cancel,
                "intent": "reports_share_cancelled",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "share_report_email", "status": "cancelled", "detail": None}],
            },
            tool_used="share_report_email",
            tools_called=[],
            raw_data_received=False,
            validation={"valid": True},
            llm_provider=None,
        )

    if not is_share_confirm_message(message):
        return None

    pending = parse_pending_share(history_text) or parse_pending_share(
        _last_assistant_from_history(conversation_history)
    )
    if not pending and chat_session_id is not None:
        from app.services.admin_client.reports.reports_share_pending import (
            latest_pending_bot_text_from_session,
        )

        pending = parse_pending_share(latest_pending_bot_text_from_session(db, chat_session_id))
    if not pending:
        return _error_turn(lang, detail="pending_parse_failed")

    try:
        from app.services.admin_client.reports import reports_tool

        share_result = reports_tool.share_report_email(
            db,
            run_id=pending.run_id,
            recipient_emails=pending.recipient_emails,
            admin_id=admin.id,
        )
    except ReportsToolError:
        return _error_turn(lang, detail="share_failed")

    plan = ReportsPlan(task_type=ReportsTaskType.report_share, profile=ReportsProfile.SHARE_DONE)
    processed = {"run": {"id": pending.run_id, "name": share_result.get("run_name")}}
    reply = compose_reports_response(processed, plan, lang=lang, share_result=share_result)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "reports_share_done",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "share_report_email", "status": "done", "detail": None}],
        },
        tool_used="share_report_email",
        tools_called=["share_report_email"],
        raw_data_received=True,
        validation={"valid": True},
        llm_provider=None,
    )


def run_reports_pipeline(
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
    from app.services.admin_client.intent_priority import should_route_reports
    from app.services.admin_client.email.email_patterns import is_send_user_email_message

    text = (message or "").strip()
    lang = _lang(ui_language, admin)

    share_turn = _handle_share_confirm(
        db,
        admin,
        text,
        lang=lang,
        history_text=history_text,
        conversation_history=conversation_history,
        chat_session_id=getattr(session, "id", None),
    )
    if share_turn is not None:
        return share_turn

    if is_send_user_email_message(text):
        return None

    if not should_route_reports(text, history_text=history_text or ""):
        return None

    plan = detect_intent(text, ui_language=lang, history_text=history_text)
    if plan is None:
        from app.services.admin_client.reports.reports_reconcile import reconcile_reports_plan
        from app.services.admin_client.reports.reports_workspace import is_reports_workspace

        if is_reports_workspace(text, history_text=history_text or ""):
            plan = reconcile_reports_plan(
                text,
                ReportsPlan(
                    task_type=ReportsTaskType.report_list_recent,
                    profile=ReportsProfile.LIST,
                    limit=15,
                ),
                history_text=history_text or "",
            )
        else:
            return None

    if plan.needs_clarification:
        return _clarify_turn(lang, plan)

    required_tools = select_required_tools(plan)
    executed = execute_tools(db, plan)
    if not executed.ok:
        if _should_partial_file_list(executed):
            return _partial_file_response(lang, executed=executed, message=text, db=db)
        return _error_turn(lang, detail=str(executed.error or "fetch_failed"))

    checked = validate_tool_results(executed, plan)
    if not checked["ok"]:
        reason = str(checked.get("reason") or "fetch_failed")
        if _should_partial_file_list(executed, reason=reason):
            return _partial_file_response(lang, executed=executed, message=text, db=db)
        return _error_turn(lang, detail=reason)

    processed = process_results_with_tools(plan=plan, executed=executed, message=text, db=db)
    tools_called = list(executed.tools_called) + list(processed.get("tools_run") or [])

    export_download = None
    if plan.task_type == ReportsTaskType.report_redownload and executed.run:
        file_ok = (executed.snapshot.get("file_available") or {}).get(int(executed.run["id"]), False)
        if file_ok:
            export_download = _build_export_download(executed.run)

    llm_provider: str | None = None
    if plan.task_type == ReportsTaskType.report_share:
        plan.profile = ReportsProfile.SHARE_PROMPT
        reply = compose_reports_response(processed, plan, lang=lang)
    elif plan.task_type == ReportsTaskType.report_preview:
        if not (processed.get("preview_summary") or {}).get("columns"):
            plan.profile = ReportsProfile.CONSULT
        reply = compose_reports_response(processed, plan, lang=lang)
    elif plan.task_type in (
        ReportsTaskType.report_list_recent,
        ReportsTaskType.report_redownload,
    ):
        reply = compose_reports_response(processed, plan, lang=lang)
    else:
        reply, llm_provider = generate_final_answer_with_llm(text, processed, plan, lang=lang)

    steps = [{"label": t, "status": "done", "detail": None} for t in tools_called]
    response = {
        "reply": reply,
        "intent": intent_for_task(plan.task_type),
        "tracking_number": None,
        "shipment": None,
        "export_download": export_download,
        "agent_steps": steps,
        "reports_plan": {"task_type": plan.task_type.value, "required_tools": required_tools},
    }
    return add_backend_metadata(
        response,
        tool_used=_primary_tool(plan),
        tools_called=tools_called,
        raw_data_received=checked["raw_data_received"],
        validation=processed.get("validation") or {},
        llm_provider=llm_provider,
    )
