"""Phase 0.5 — exports plateforme admin déterministes (logs / suivi plateforme) en simple mode.

Le suivi FedEx live, la lecture de documents, les notifications et les exports PDF/Excel
« conversationnels » (style client) sont désormais gérés en amont par le pipeline
`admin_client` (voir `app.services.admin_client.pipeline.run_admin_client_turn`).

Ce bridge ne conserve que les exports plateforme administrateur whitelistés
(`export_activity_logs_pdf/excel`, `export_tracking_pdf`), qui n'ont pas d'équivalent
côté client. Toute la logique de résolution de numéro de suivi maison a été retirée :
elle était tronquée et résolvait mal les relances (remplacée par `chat_session_context`).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.activity_log_service import write_log
from app.services.ai_assistant.tool_executor import build_tool_context
from app.services.ai_assistant.tool_planner import plan_export_tools
from app.services.ai_assistant.tool_registry import resolve_handler
from app.services.gpt.tool_executor import execute_tool
from app.services.gpt.tool_synthesis import synthesize_tool_results
from app.services.gpt.tool_types import ToolCall

from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request
from app.services.chat_session_context import resolve_tracking_from_history_text
from app.services.client_phase3.pdf_postprocess import wants_pdf_format
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number

logger = logging.getLogger(__name__)

_ALLOWED_TOOLS = frozenset({
    "export_tracking_pdf",
    "export_activity_logs_pdf",
    "export_activity_logs_excel",
})

_TOOL_ALIASES: dict[str, str] = {
    "export_tracking_status_pdf": "export_tracking_pdf",
}


def _normalize_tool_name(name: str) -> str:
    return _TOOL_ALIASES.get(name, resolve_handler(name))


def _history_text(conversation_history: list[dict[str, str]] | None) -> str:
    lines: list[str] = []
    for raw in conversation_history or []:
        if isinstance(raw, dict):
            content = str(raw.get("content") or "").strip()
        else:
            content = str(getattr(raw, "content", "") or "").strip()
        if content:
            lines.append(content)
    return "\n".join(lines)


def _skip_admin_tracking_pdf_bridge(
    message: str,
    conversation_history: list[dict[str, str]] | None,
) -> bool:
    """PDF colis/followup admin — géré par admin_client, pas export_tracking_pdf."""
    text = (message or "").strip()
    hist = _history_text(conversation_history)
    has_session = bool(resolve_tracking_from_history_text(hist))
    # Export plateforme bulk (sans TN) — rester sur export_tracking_pdf du bridge.
    if wants_pdf_format(text) and re.search(
        r"\b(exporte?|exporter)\s+(les\s+)?colis\b|\btous les colis\b", text, re.I
    ) and not extract_tracking_number(text):
        return False
    if is_admin_shipment_pdf_request(text, has_session_tracking=has_session):
        return True
    if wants_pdf_format(message):
        tn = extract_tracking_number(message or "")
        if tn and is_plausible_tracking_number(tn):
            return True
        if resolve_tracking_from_history_text(hist):
            return True
    return False


def _plan_export_actions(
    message: str,
    conversation_history: list[dict[str, str]] | None,
    *,
    agent_mode: bool,
) -> list[tuple[str, dict[str, Any]]] | None:
    if not agent_mode:
        return None
    planned = plan_export_tools(message, conversation_history)
    if not planned:
        return None
    filtered: list[tuple[str, dict[str, Any]]] = []
    skip_tracking_pdf = _skip_admin_tracking_pdf_bridge(message, conversation_history)
    for name, args in planned:
        canonical = _normalize_tool_name(name)
        if canonical == "export_tracking_pdf" and skip_tracking_pdf:
            continue
        if canonical in _ALLOWED_TOOLS:
            filtered.append((canonical, dict(args or {})))
    return filtered or None


def _execute_planned_tools(
    db: Session,
    admin: User,
    planned: list[tuple[str, dict[str, Any]]],
    *,
    ui_language: str,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any] | None, bool]:
    tool_ctx = build_tool_context(
        db,
        admin,
        analysis_mode=False,
        ui_language=ui_language,
    )
    tool_payloads: list[dict[str, Any]] = []
    tools_used: list[str] = []
    export_download: dict[str, Any] | None = None
    action_executed = False

    for name, args in planned:
        canonical = _normalize_tool_name(name)
        if canonical not in _ALLOWED_TOOLS:
            continue
        result = execute_tool(tool_ctx, ToolCall(name=canonical, args=args))
        resp = result.to_function_response()
        tool_payloads.append({"name": canonical, "response": resp})
        if canonical not in tools_used:
            tools_used.append(canonical)
        if result.success and result.data.get("export_download"):
            export_download = result.data["export_download"]
            action_executed = True
        elif result.success and result.data.get("action_executed"):
            action_executed = True

    return tool_payloads, tools_used, export_download, action_executed


def try_admin_simple_actions(
    db: Session,
    admin: User,
    message: str,
    *,
    conversation_history: list[dict[str, str]] | None = None,
    ui_language: str = "fr",
    agent_mode: bool = False,
    ip_address: str = "",
    started: float | None = None,
) -> dict[str, Any] | None:
    """
    Phase 0.5 — exécute uniquement les exports plateforme whitelistés sans pipeline complet.
    Retourne None si aucune action reconnue (fallback Ollama).
    """
    t0 = started if started is not None else time.perf_counter()
    lang = (ui_language or "fr").lower()[:2]

    planned_export = _plan_export_actions(message, conversation_history, agent_mode=agent_mode)
    if not planned_export:
        return None

    tool_payloads, tools_used, export_download, action_executed = _execute_planned_tools(
        db, admin, planned_export, ui_language=lang,
    )
    if not tool_payloads:
        return None

    intent = "export"
    from app.services.globex_agent import kernel as kernel_mod

    local_reply = synthesize_tool_results(tool_payloads, ui_language=lang) or ""
    llm_reply, llm_degraded = kernel_mod._humanize_action_with_ollama(
        message=message,
        tool_payloads=tool_payloads,
        ui_language=lang,
        local_reply=local_reply,
    )
    if not llm_reply:
        llm_reply, llm_degraded = kernel_mod._fallback_reply(
            message=message,
            tool_payloads=tool_payloads,
            ui_language=lang,
            llm_reply=local_reply,
        )

    final_reply, synth_degraded = kernel_mod._build_final_reply(
        llm_reply=llm_reply,
        tool_payloads=tool_payloads,
        export_download=export_download,
        needs_approval=False,
        approval_hint=None,
        message=message,
        ui_language=lang,
    )
    if synth_degraded:
        llm_degraded = True

    final_reply = kernel_mod._sanitize_false_export_claims(final_reply, export_download)
    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    write_log(
        db,
        action="globex_agent.chat",
        message=message[:120],
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=ip_address,
        metadata={
            "agent_mode": agent_mode,
            "tools": tools_used,
            "orchestrator": "simple_bridge",
            "simple_mode": True,
            "intent": intent,
        },
    )
    db.commit()

    return {
        "reply": final_reply,
        "mode": "jarvis",
        "tools_used": tools_used,
        "agent_steps": [
            {
                "label": item.get("name", "tool"),
                "status": "done",
                "detail": json.dumps(item.get("response") or {}, ensure_ascii=False)[:120],
            }
            for item in tool_payloads
        ],
        "needs_approval": False,
        "approval_id": None,
        "approval_hint": None,
        "mission_id": None,
        "action_executed": action_executed,
        "export_download": export_download,
        "llm_degraded": llm_degraded,
        "intent": intent,
        "execution_time_ms": elapsed,
        "shipment": None,
    }
