"""Context Export Engine — exporte le dernier résultat sans re-recherche."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.conversation_state import ConversationState
from app.services.ai_assistant.entity_memory import EntityMemory, is_contextual_reference
from app.services.ai_assistant.export_normalize import ExportDataError, parse_export_limit
from app.services.ai_assistant.export_pipeline import (
    build_export_response_spec,
    export_tool_name,
    prepare_export_dataset,
)
from app.services.ai_assistant.intent_classifier_v2 import CopilotIntent, classify_copilot_intent
from app.services.ai_assistant.intent_router_v2 import IntentV2, classify_intent_v2
from app.services.gpt.copilot_conversation_state import (
    CopilotConversationState,
    merge_conversation_state,
    parse_limit_from_message,
    resolve_copilot_turn,
    update_state_after_tools,
)

logger = logging.getLogger(__name__)

_MODULE_LABELS = {
    "notifications": "notifications",
    "tracking": "opérations tracking",
    "users": "utilisateurs",
    "tickets": "tickets",
    "conversations": "conversations",
    "logs": "journaux",
}


def is_contextual_export_request(
    message: str,
    *,
    copilot_state: dict[str, Any] | None = None,
    memory: EntityMemory | None = None,
) -> bool:
    state = CopilotConversationState.from_dict(copilot_state)
    intent = classify_intent_v2(message, memory=memory)
    if intent.action == "EXPORT" and intent.is_contextual_reference:
        return True
    if intent.action == "EXPORT" and (state.last_exportable_result or (memory and memory.has_exportable_context())):
        return True
    resolved = resolve_copilot_turn(message, state)
    return resolved.kind == "contextual_export"


def _items_from_memory(
    state: CopilotConversationState,
    memory: EntityMemory,
    *,
    module: str,
) -> list[dict[str, Any]]:
    if state.last_items and state.last_module == module:
        return list(state.last_items)
    if module == "notifications" and memory.last_notifications:
        return list(memory.last_notifications)
    if module == "users" and memory.last_export_dataset:
        return list(memory.last_export_dataset)
    if module == "logs" and memory.last_logs:
        return list(memory.last_logs)
    if module == "tickets" and memory.last_ticket_items:
        return list(memory.last_ticket_items)
    if memory.last_export_dataset and memory.last_module == module:
        return list(memory.last_export_dataset)
    return []


def _export_error_response(
    *,
    error: str,
    agent_type: str,
    state: CopilotConversationState,
    ui_lang: str,
) -> dict[str, Any]:
    return {
        "reply": error,
        "intent": "admin_export",
        "agent_type": agent_type,
        "agent_type_label": "Copilot Globex",
        "action_executed": False,
        "analysis_only": True,
        "tools_used": [],
        "copilot_state": state.to_dict(),
        "llm_provider": "local",
        "gpt_slug": "fedex-admin-ops",
        "error": error,
        "language": ui_lang,
    }


def try_context_export_turn(
    db: Session,
    admin: User,
    message: str,
    *,
    copilot_state: dict[str, Any] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    agent_mode: bool = False,
    agent_type: str = "summary",
) -> dict[str, Any] | None:
    state = merge_conversation_state(copilot_state, conversation_history)
    state_dict = copilot_state or state.to_dict()
    memory = EntityMemory.from_copilot_state(state_dict)
    conv = ConversationState.from_copilot_state(state_dict)
    copilot_intent = classify_copilot_intent(message, copilot_state=state_dict)
    _no_export_intents = {
        CopilotIntent.SUSPICIOUS_ACTIVITY, CopilotIntent.NOTIFICATION_FREQUENCY,
        CopilotIntent.TOP_ACTIVE_USERS, CopilotIntent.PLATFORM_HEALTH_REPORT,
        CopilotIntent.SECURITY_REPORT, CopilotIntent.CRITICAL_INCIDENTS,
        CopilotIntent.USER_COUNT, CopilotIntent.COUNT_ACTIVE_USERS,
        CopilotIntent.USER_LIST, CopilotIntent.LIST_ACTIVE_USERS,
        CopilotIntent.NOTIFICATION_LIST, CopilotIntent.TRACKING_LIST,
        CopilotIntent.TICKET_QUERY, CopilotIntent.TOP_PLATFORM_ISSUES,
        CopilotIntent.LIST_SUSPENDED_USERS, CopilotIntent.SECURITY_ALERTS,
        CopilotIntent.OPEN_INCIDENTS, CopilotIntent.CRITICAL_TICKETS,
        CopilotIntent.LIST_SUSPENDABLE_USERS, CopilotIntent.EXPORT_SUSPENDABLE_USERS,
    }
    if copilot_intent.name in _no_export_intents:
        return None

    intent = classify_intent_v2(message, memory=memory)

    # Export historique colis unique — priorité sur export global
    tn = conv.last_tracking_number or memory.last_tracking_number
    from app.services.ai_assistant.tracking_history_export import try_export_tracking_history
    tracking_export = try_export_tracking_history(
        db, admin, message,
        tracking_number=tn or "",
        copilot_state=state_dict,
        lang=admin.preferred_language or "fr",
    ) if tn else None
    if tracking_export:
        return tracking_export

    # platform_health_report ne doit jamais être export
    from app.services.ai_assistant.intent_priority import _PLATFORM_HEALTH_RE
    if _PLATFORM_HEALTH_RE.search(message):
        return None

    contextual = is_contextual_reference(message) or intent.is_contextual_reference or (
        bool(state.last_exportable_result and intent.action == "EXPORT")
    )

    explicit_limit: int | None = None
    fmt = "pdf"

    if intent.action != "EXPORT":
        resolved = resolve_copilot_turn(message, state, messages=conversation_history)
        if resolved.kind != "contextual_export":
            return None
        module = resolved.module or state.last_module or memory.last_module or "generic"
        fmt = resolved.export_format or "pdf"
        explicit_limit = resolved.limit
    else:
        module = intent.domain if intent.domain != "generic" else None
        if contextual or intent.is_contextual_reference:
            module = state.last_module or memory.last_module or module
        else:
            module = module or state.last_module or memory.last_module
        fmt = intent.export_format or "pdf"
        explicit_limit = intent.limit
        if not module or module == "generic":
            resolved = resolve_copilot_turn(message, state, messages=conversation_history)
            if resolved.kind == "clarify_export":
                from app.services.gpt.copilot_context_resolver import clarify_export_reply

                clarify_text, clarify_provider = clarify_export_reply(
                    admin.preferred_language or "fr", message,
                )
                return {
                    "reply": clarify_text,
                    "intent": "admin_export",
                    "agent_type": agent_type,
                    "agent_type_label": "Copilot Globex",
                    "action_executed": False,
                    "analysis_only": True,
                    "tools_used": [],
                    "copilot_state": state.to_dict(),
                    "llm_provider": clarify_provider,
                    "gpt_slug": "fedex-admin-ops",
                }
            module = resolved.module or module
            explicit_limit = explicit_limit or resolved.limit

    if not module or module == "generic":
        return None

    items = _items_from_memory(state, memory, module=module)
    if not items and conv.last_exportable_dataset:
        ds = conv.last_exportable_dataset
        if isinstance(ds, dict) and ds.get("type") == module and ds.get("data"):
            items = list(ds["data"])
    if not items and module == "logs" and not agent_mode:
        return None

    if not items:
        from app.services.gpt.copilot_context_resolver import ResolvedCopilotTurn, execute_contextual_export

        resolved = ResolvedCopilotTurn(
            kind="contextual_export",
            module=module,
            export_format=fmt if fmt in ("pdf", "xlsx") else "pdf",
            limit=explicit_limit or state.last_limit or parse_export_limit(message) or 10,
        )
        return execute_contextual_export(
            db, admin, resolved, state,
            agent_mode=agent_mode,
            user_message=message,
        )

    ui_lang = admin.preferred_language or "fr"
    generated_by = admin.full_name or admin.email or "Administrateur Globex"
    state_limit = state.last_limit or memory.last_limit or parse_limit_from_message(message)

    try:
        normalized, records, filename, _pdf_bytes, export_token = prepare_export_dataset(
            items,
            module=module,
            message=message,
            admin_id=admin.id,
            contextual=contextual,
            state_limit=state_limit,
            explicit_limit=explicit_limit,
            source="context_memory",
            fmt=fmt if fmt in ("pdf", "xlsx", "docx") else "pdf",
            generated_by=str(generated_by),
        )
    except ExportDataError as exc:
        logger.warning("[EXPORT] validation_failed module=%s error=%s", module, exc)
        return _export_error_response(error=str(exc), agent_type=agent_type, state=state, ui_lang=ui_lang)

    export_spec = build_export_response_spec(
        module=module,
        filename=filename,
        records=records,
        export_token=export_token,
        fmt=fmt if fmt in ("pdf", "xlsx") else "pdf",
        limit=records,
    )

    export_tool = export_tool_name(module)
    label = _MODULE_LABELS.get(module, module)
    reply = (
        f"PDF généré avec succès : **{records}** {label} exporté(s).\n"
        f"Téléchargez : **{filename}**"
        if ui_lang == "fr"
        else f"PDF generated: **{records}** {label} exported.\nDownload: **{filename}**"
    )

    state = update_state_after_tools(
        state,
        tools_used=[export_tool],
        tool_payloads=[{
            "name": export_tool,
            "response": {
                "status": "ok",
                "export_ready": True,
                "count": records,
                "filename": filename,
                "export_download": export_spec,
            },
        }],
        reply_summary=reply[:200],
    )
    memory.last_export_dataset = normalized
    state_dict = state.to_dict()
    state_dict.update(memory.to_state_updates())

    return {
        "reply": reply,
        "intent": f"export_{module}_pdf",
        "agent_type": agent_type,
        "agent_type_label": "Copilot Globex",
        "action_executed": True,
        "analysis_only": False,
        "tools_used": [export_tool],
        "export_download": export_spec,
        "file_name": filename,
        "records": records,
        "error": None,
        "copilot_state": state_dict,
        "language": ui_lang,
        "llm_provider": "local",
        "gpt_slug": "fedex-admin-ops",
    }
