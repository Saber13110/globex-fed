"""Résolution contextuelle et export — sans mot-clé « pdf » → logs."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.copilot_export_service import build_export_download_spec
from app.services.gpt.copilot_conversation_state import (
    CopilotConversationState,
    ResolvedCopilotTurn,
    update_state_after_tools,
)
from app.services.gpt.orchestrator import SLUG_ADMIN
from app.services.gpt.tool_handlers import HANDLERS
from app.services.gpt.tool_synthesis import synthesize_copilot_reply
from app.services.gpt.tool_types import ToolExecutionContext

logger = logging.getLogger(__name__)

_MODULE_LABELS = {
    "notifications": "notifications",
    "tracking": "opérations tracking",
    "users": "utilisateurs",
    "tickets": "tickets",
    "conversations": "conversations",
    "logs": "journaux",
}

_EXPORT_TOOL_NAMES = {
    "notifications": "export_notifications_pdf",
    "tracking": "export_tracking_status_pdf",
    "users": "export_users_pdf",
    "tickets": "export_tickets_pdf",
    "conversations": "export_conversations_pdf",
    "logs": "export_activity_logs_pdf",
}


def _fetch_module_data(
    db: Session,
    admin: User,
    *,
    module: str,
    limit: int,
    state: CopilotConversationState,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Récupère les données — réutilise l'état si le module correspond."""
    if (
        state.last_module == module
        and state.last_payload
        and state.last_items
        and (state.last_limit or 0) <= limit + 5
    ):
        return state.last_tool_used or f"analyze_{module}", state.last_payload, state.last_items

    tool_map = {
        "notifications": ("analyze_notifications", {"limit": limit}),
        "logs": ("analyze_logs", {"hours": 24, "limit": limit}),
        "tracking": ("analyze_tracking", {"limit": limit}),
        "users": ("analyze_users", {"limit": limit}),
        "tickets": ("analyze_tickets", {"status": "open", "limit": limit}),
        "conversations": ("analyze_conversations", {"limit": limit}),
        "security": ("analyze_security", {"limit": limit}),
        "reports": ("analyze_reports", {"tracking_limit": limit, "ticket_limit": limit}),
    }
    tool_name, args = tool_map.get(module, ("analyze_reports", {}))
    handler = HANDLERS.get(tool_name)
    if handler is None:
        return tool_name, {}, []

    ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role="admin",
        gpt_slug=SLUG_ADMIN,
        actor_admin_id=admin.id,
        ui_language=admin.preferred_language or "fr",
    )
    result = handler(ctx, args)
    if not result.success:
        return tool_name, {}, []
    data = dict(result.data)
    sample = (
        data.get("sample")
        or data.get("tickets")
        or data.get("users")
        or data.get("documents")
        or []
    )
    if not isinstance(sample, list):
        sample = []
    return tool_name, data, [x for x in sample if isinstance(x, dict)]


def _gemini_reply(
    *,
    task: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str,
    fallback: str,
    extra_instruction: str = "",
) -> tuple[str, str]:
    return synthesize_copilot_reply(
        task=task,
        tool_payloads=tool_payloads,
        ui_language=ui_language,
        fallback=fallback,
        extra_instruction=extra_instruction,
    )


def execute_contextual_export(
    db: Session,
    admin: User,
    resolved: ResolvedCopilotTurn,
    state: CopilotConversationState,
    *,
    agent_mode: bool,
    user_message: str = "",
) -> dict[str, Any] | None:
    if resolved.kind != "contextual_export" or not resolved.module:
        return None

    module = resolved.module
    limit = resolved.limit or state.last_limit or 10
    fmt = resolved.export_format or "pdf"
    ui_lang = admin.preferred_language or "fr"
    task = (user_message or "").strip() or f"Export {fmt} des {_MODULE_LABELS.get(module, module)}"

    if fmt == "xlsx" and module == "logs":
        from app.services.gpt.tool_handlers import HANDLERS as H

        handler = H.get("export_activity_logs_excel")
        if handler and agent_mode:
            ctx = ToolExecutionContext(
                db=db, user_id=admin.id, user_role="admin", gpt_slug=SLUG_ADMIN,
                actor_admin_id=admin.id, ui_language=ui_lang,
                analysis_mode=not agent_mode,
            )
            result = handler(ctx, {"hours": 24})
            if result.success and result.data.get("export_download"):
                spec = result.data["export_download"]
                fallback = (
                    f"Export Excel prêt — téléchargez **{spec.get('filename', 'export.xlsx')}**."
                )
                reply, provider = _gemini_reply(
                    task=task,
                    tool_payloads=[{
                        "name": "export_activity_logs_excel",
                        "response": {"status": "ok", "export_download": spec, **result.data},
                    }],
                    ui_language=ui_lang,
                    fallback=fallback,
                    extra_instruction=(
                        "Confirmez que l'export Excel des journaux est prêt. "
                        "Mentionnez le nom du fichier. Une phrase courte."
                    ),
                )
                return _export_response(
                    module="logs",
                    tool="export_activity_logs_excel",
                    reply=reply,
                    export_spec=spec,
                    state=state,
                    items=[],
                    llm_provider=provider,
                )

    if not agent_mode and module == "logs":
        fallback = (
            "Pour exporter les journaux en PDF ou Excel, activez le **mode Agent** "
            "dans l'en-tête du copilot."
        )
        reply, provider = _gemini_reply(
            task=task,
            tool_payloads=[{
                "name": "export_blocked",
                "response": {
                    "status": "ok",
                    "reason": "analysis_mode",
                    "required_mode": "agent",
                    "module": "logs",
                },
            }],
            ui_language=ui_lang,
            fallback=fallback,
            extra_instruction=(
                "L'export des journaux nécessite le mode Agent. Expliquez brièvement, sans liste de capacités."
            ),
        )
        return _export_response(
            module=module,
            tool="",
            reply=reply,
            export_spec=None,
            state=state,
            items=[],
            action_executed=False,
            llm_provider=provider,
        )

    tool_used, data, items = _fetch_module_data(
        db, admin, module=module, limit=limit, state=state,
    )

    if not items:
        fallback = "Je n'ai pas accès à cette donnée pour le moment."
        reply, provider = _gemini_reply(
            task=task,
            tool_payloads=[{
                "name": tool_used or f"analyze_{module}",
                "response": {"status": "error", "error": "no_data", **data},
            }],
            ui_language=ui_lang,
            fallback=fallback,
        )
        return {
            "reply": reply,
            "tools_used": [tool_used] if tool_used else [],
            "copilot_state": state.to_dict(),
            "llm_provider": provider,
            "gpt_slug": SLUG_ADMIN,
        }

    from app.services.ai_assistant.entity_memory import is_contextual_reference
    from app.services.ai_assistant.export_normalize import ExportDataError
    from app.services.ai_assistant.export_pipeline import (
        build_export_response_spec,
        export_tool_name,
        prepare_export_dataset,
    )

    generated_by = admin.full_name or admin.email or "Administrateur Globex"
    contextual = bool(state.last_items and state.last_module == module) or is_contextual_reference(task)
    source = "context_memory" if contextual and state.last_items else "refetch"

    try:
        normalized, records, filename, _pdf, export_token = prepare_export_dataset(
            items,
            module=module,
            message=task,
            admin_id=admin.id,
            contextual=contextual,
            state_limit=state.last_limit,
            explicit_limit=limit,
            source=source,
            fmt=fmt if fmt in ("pdf", "xlsx") else "pdf",
            generated_by=str(generated_by),
        )
    except ExportDataError as exc:
        return {
            "reply": str(exc),
            "tools_used": [],
            "copilot_state": state.to_dict(),
            "llm_provider": "local",
            "gpt_slug": SLUG_ADMIN,
            "error": str(exc),
        }

    export_spec = build_export_response_spec(
        module=module,
        filename=filename,
        records=records,
        export_token=export_token,
        fmt=fmt if fmt in ("pdf", "xlsx") else "pdf",
        limit=records,
    )
    if module == "tracking":
        numbers = ",".join(
            str(x.get("tracking_number") or x.get("numero") or "").strip()
            for x in items
            if x.get("tracking_number") or x.get("numero")
        )[:500]
        if numbers:
            export_spec["tracking_numbers"] = numbers

    label = _MODULE_LABELS.get(module, module)
    export_tool = export_tool_name(module)
    fallback = (
        f"PDF généré avec succès : **{records}** {label} exporté(s).\n"
        f"Téléchargez : **{filename}**."
    )
    reply, provider = _gemini_reply(
        task=task,
        tool_payloads=[{
            "name": export_tool,
            "response": {
                "status": "ok",
                "export_ready": True,
                "format": fmt,
                "module": module,
                "count": records,
                "records": records,
                "filename": filename,
                "export_download": export_spec,
                "preview": normalized[:5],
            },
        }],
        ui_language=ui_lang,
        fallback=fallback,
        extra_instruction=(
            f"L'export {fmt.upper()} est prêt ({records} élément(s), fichier {filename}). "
            "Confirmez brièvement en français et indiquez que l'utilisateur peut télécharger le fichier."
        ),
    )

    new_state = update_state_after_tools(
        state,
        tools_used=[tool_used],
        tool_payloads=[{"name": tool_used, "response": {"status": "ok", **data}}],
    )
    new_state.last_format = fmt

    return _export_response(
        module=module,
        tool=export_tool,
        reply=reply,
        export_spec=export_spec,
        state=new_state,
        items=normalized,
        llm_provider=provider,
    )


def _export_response(
    *,
    module: str,
    tool: str,
    reply: str,
    export_spec: dict[str, Any] | None,
    state: CopilotConversationState,
    items: list[dict],
    action_executed: bool = True,
    llm_provider: str = "gemini",
) -> dict[str, Any]:
    state.last_module = module
    state.last_exportable_result = True
    return {
        "reply": reply,
        "intent": f"admin_{module}",
        "agent_type": module,
        "agent_type_label": "Copilot Globex",
        "mission_id": None,
        "action_executed": action_executed and bool(export_spec),
        "needs_approval": False,
        "approval_id": None,
        "analysis_only": not action_executed,
        "agent_steps": [{"label": tool or module, "status": "done", "detail": None}] if tool else [],
        "agent_reasoning": None,
        "conversation_id": None,
        "export_download": export_spec,
        "agent_questionnaire": None,
        "llm_degraded": llm_provider == "degraded",
        "llm_provider": llm_provider,
        "gpt_slug": SLUG_ADMIN,
        "knowledge_hits": 0,
        "tools_used": [tool] if tool else [],
        "copilot_state": state.to_dict(),
    }


def clarify_export_reply(lang: str = "fr", user_message: str = "") -> tuple[str, str]:
    """Demande de précision export — via Gemini, repli template si indisponible."""
    static_fr = (
        "Quel contenu souhaitez-vous exporter en PDF — "
        "**notifications**, **tracking**, **journaux**, **utilisateurs**, **tickets** ou un **rapport** ?"
    )
    static_en = (
        "Which content would you like to export as PDF — "
        "notifications, tracking, logs, users, tickets, or a report?"
    )
    fallback = static_en if lang == "en" else static_fr
    task = (user_message or "").strip() or "L'utilisateur souhaite un export PDF sans préciser le contenu."
    return _gemini_reply(
        task=task,
        tool_payloads=[{
            "name": "clarify_export",
            "response": {
                "status": "ok",
                "action": "ask_module",
                "options": ["notifications", "tracking", "logs", "users", "tickets", "rapport"],
            },
        }],
        ui_language=lang,
        fallback=fallback,
        extra_instruction=(
            "Demandez poliment quel contenu exporter (notifications, tracking, journaux, "
            "utilisateurs, tickets ou rapport). Une ou deux phrases maximum."
        ),
    )
