"""
Pipeline Copilot intelligent — architecture modulaire au-dessus de l'existant.

query → detect_language → load_conversation_state → context_resolver →
intent_classifier_v2 → tool_router → safe_tool_executor →
deterministic_answer_engine → response_formatter → update_conversation_state
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.context_resolver import resolve_context
from app.services.ai_assistant.conversation_state import ConversationState
from app.services.ai_assistant.deterministic_answer_engine import build_deterministic_answer
from app.services.ai_assistant.entity_memory import EntityMemory
from app.services.ai_assistant.intent_classifier_v2 import CopilotIntent, classify_copilot_intent
from app.services.ai_assistant.language_service import resolve_response_language
from app.services.ai_assistant.response_formatter import build_clean_api_response, finalize_reply
from app.services.ai_assistant.safe_tool_executor import GLOBAL_DEADLINE_S, execute_tool_plan
from app.services.ai_assistant.tool_router import route_tools
from app.services.ai_assistant.tracking_history_export import try_export_tracking_history

logger = logging.getLogger(__name__)


def _finish(conv: ConversationState, base: dict[str, Any], copilot_state: dict[str, Any] | None) -> dict[str, Any]:
    base["copilot_state"] = conv.merge_into_copilot_state(dict(copilot_state or {}))
    return build_clean_api_response(base)


def _conversation_memory_payload(intent, conv: ConversationState) -> dict[str, Any] | None:
    """Fallback CAS 7 — données déjà chargées en session."""
    name = intent.name
    if name in {
        CopilotIntent.USER_COUNT, CopilotIntent.COUNT_ACTIVE_USERS,
        CopilotIntent.USER_LIST, CopilotIntent.LIST_ACTIVE_USERS,
        CopilotIntent.LIST_SUSPENDED_USERS,
    }:
        return conv.last_users_result if isinstance(conv.last_users_result, dict) else None
    if name in {
        CopilotIntent.SUSPICIOUS_ACTIVITY, CopilotIntent.SECURITY_REPORT,
        CopilotIntent.CRITICAL_INCIDENTS, CopilotIntent.SECURITY_ALERTS,
        CopilotIntent.OPEN_INCIDENTS,
    }:
        return conv.last_security_result if isinstance(conv.last_security_result, dict) else None
    if name in {CopilotIntent.TICKET_QUERY, CopilotIntent.CRITICAL_TICKETS}:
        return conv.last_ticket_result if isinstance(conv.last_ticket_result, dict) else None
    if name in {CopilotIntent.NOTIFICATION_LIST, CopilotIntent.NOTIFICATION_FREQUENCY}:
        return conv.last_notifications_result if isinstance(conv.last_notifications_result, dict) else None
    if name in {CopilotIntent.PLATFORM_HEALTH_REPORT, CopilotIntent.TOP_PLATFORM_ISSUES}:
        return conv.last_report_result if isinstance(conv.last_report_result, dict) else None
    return None


def _handle_export(
    db: Session,
    admin: User,
    message: str,
    *,
    intent,
    conv: ConversationState,
    rctx,
    copilot_state: dict[str, Any] | None,
    conversation_history: list | None,
    agent_type: str,
    lang: str,
    route,
) -> dict[str, Any] | None:
    tn = intent.tracking_number or conv.last_tracking_number
    if route.export_module == "tracking_history" and tn:
        result = try_export_tracking_history(
            db, admin, message, tracking_number=tn,
            copilot_state=copilot_state, lang=lang,
        )
        if result:
            conv.record_tool_success("get_tracking_by_number", conv.last_tracking_result or {}, intent=intent.name.value)
            return _finish(conv, result, copilot_state)

    # Export profil utilisateur unique
    if route.export_single and conv.last_selected_user:
        user = conv.last_selected_user
        conv.last_exportable_result = {"type": "users", "data": [user]}
        conv.last_exportable_dataset = conv.last_exportable_result
        state = conv.merge_into_copilot_state(dict(copilot_state or {}))
        from app.services.ai_assistant.context_export_engine import try_context_export_turn
        export = try_context_export_turn(
            db, admin, message,
            copilot_state=state,
            conversation_history=conversation_history,
            agent_type=agent_type,
        )
        if export:
            export["language"] = lang
            if export.get("reply"):
                export["reply"] = finalize_reply(export["reply"], language=lang)
                export["answer"] = export["reply"]
            return _finish(conv, export, copilot_state)
        return None

    from app.services.ai_assistant.context_export_engine import try_context_export_turn
    export = try_context_export_turn(
        db, admin, message,
        copilot_state=conv.merge_into_copilot_state(dict(copilot_state or {})),
        conversation_history=conversation_history,
        agent_type=agent_type,
    )
    if export:
        export["language"] = lang
        if export.get("reply"):
            export["reply"] = finalize_reply(export["reply"], language=lang)
            export["answer"] = export["reply"]
        return _finish(conv, export, copilot_state)
    return None


def run_copilot_pipeline(
    db: Session,
    admin: User,
    message: str,
    *,
    copilot_state: dict[str, Any] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    agent_type: str = "summary",
) -> dict[str, Any] | None:
    lang, _ = resolve_response_language(
        message,
        profile_language=admin.preferred_language,
        session_language=(copilot_state or {}).get("last_language"),
    )
    conv = ConversationState.from_copilot_state(copilot_state)
    conv.last_language = lang
    memory = EntityMemory.from_copilot_state(copilot_state)

    rctx = resolve_context(message, conv=conv, memory=memory, language=lang)
    intent = classify_copilot_intent(
        message, conv=conv, memory=memory, copilot_state=copilot_state, resolved_ctx=rctx,
    )
    deadline = time.monotonic() + GLOBAL_DEADLINE_S
    logger.info("[Pipeline] intent=%s follow_up=%s", intent.name.value, rctx.follow_up_kind)

    if intent.name == CopilotIntent.UNKNOWN:
        return None

    if intent.name == CopilotIntent.GREETING:
        return None  # géré en amont par admin_copilot_service

    # --- Handlers ciblés rapides (top issues, suspendus, suspect, alertes) ---
    from app.services.ai_assistant.targeted_handlers import try_targeted_handler
    targeted = try_targeted_handler(
        db, admin, message, intent=intent, conv=conv, lang=lang,
    )
    if targeted:
        return _finish(conv, targeted, copilot_state)

    route = route_tools(intent, conv_tracking_number=conv.last_tracking_number)

    # --- Exports contextuels ---
    if intent.name == CopilotIntent.EXPORT_CONTEXTUAL or intent.is_export:
        result = _handle_export(
            db, admin, message,
            intent=intent, conv=conv, rctx=rctx,
            copilot_state=copilot_state, conversation_history=conversation_history,
            agent_type=agent_type, lang=lang, route=route,
        )
        if result:
            return result
        if intent.is_export:
            return None

    # --- Catalogues agents/outils ---
    if intent.name == CopilotIntent.AGENT_CATALOG:
        from app.services.admin_copilot_service import format_agent_catalog_reply
        return _finish(conv, {
            "reply": format_agent_catalog_reply(agent_mode=False),
            "language": lang, "mode": "deterministic",
            "intent": intent.name.value, "tools_used": [], "confidence": 0.95,
        }, copilot_state)

    if intent.name == CopilotIntent.TOOL_CATALOG:
        from app.services.admin_copilot_service import format_tools_catalog_reply
        return _finish(conv, {
            "reply": format_tools_catalog_reply(agent_mode=False),
            "language": lang, "mode": "deterministic",
            "intent": intent.name.value, "tools_used": [], "confidence": 0.95,
        }, copilot_state)

    # --- Exécution outils ---
    tool_results: list[dict[str, Any]] = []
    if route.plan and not route.memory_only:
        tool_results = execute_tool_plan(
            db, admin, route.plan, deadline=deadline, ui_language=lang,
        )
        for tr in tool_results:
            if tr.get("ok"):
                conv.record_tool_success(tr["name"], tr["response"], intent=intent.name.value)

        # Fallback CAS 7 : cache top issues ou mémoire conversation
        if not any(r.get("ok") for r in tool_results):
            if intent.name == CopilotIntent.PLATFORM_HEALTH_REPORT:
                from app.services.ai_assistant.targeted_handlers import get_top_platform_issues
                answer, tools, from_cache = get_top_platform_issues(db, admin, message, lang=lang)
                return _finish(conv, {
                    "reply": answer, "language": lang, "mode": "deterministic",
                    "intent": intent.name.value, "tools_used": tools,
                    "confidence": 0.85 if from_cache else 0.88,
                }, copilot_state)
            mem_payload = _conversation_memory_payload(intent, conv)
            if mem_payload:
                tool_results = [{"name": "conversation_memory", "ok": True, "response": mem_payload}]

    answer, tools_used, confidence = build_deterministic_answer(
        intent, conv=conv, rctx=rctx, tool_results=tool_results, language=lang,
    )
    if not answer:
        return None

    return _finish(conv, {
        "reply": answer,
        "language": lang,
        "mode": "deterministic",
        "intent": intent.name.value,
        "tools_used": tools_used,
        "confidence": confidence,
    }, copilot_state)


def try_copilot_pipeline(*args, **kwargs) -> dict[str, Any] | None:
    return run_copilot_pipeline(*args, **kwargs)
