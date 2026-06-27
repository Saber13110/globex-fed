"""
Moteur de réponse déterministe — ne dépend jamais de Gemini pour count/list/follow-up/export.
"""

from __future__ import annotations

from typing import Any

from app.services.ai_assistant.context_resolver import ResolvedContext
from app.services.ai_assistant.conversation_state import ConversationState
from app.services.ai_assistant.deterministic_analytics import (
    format_notification_frequency,
    format_platform_health_fast,
    format_security_report_fast,
    format_suspicious_activity_fast,
    format_top_active_users,
)
from app.services.ai_assistant.intent_classifier_v2 import ClassifiedIntent, CopilotIntent
from app.services.ai_assistant.response_formatter import (
    format_security_for_user,
    format_tickets_for_user,
    format_tracking_creator,
    format_tracking_delay,
    format_tracking_duration,
    format_tracking_for_user,
    format_user_email,
    format_user_role,
    format_users_list,
    format_user_profile,
)


def build_deterministic_answer(
    intent: ClassifiedIntent,
    *,
    conv: ConversationState,
    rctx: ResolvedContext,
    tool_results: list[dict[str, Any]],
    language: str = "fr",
) -> tuple[str, list[str], float]:
    """Retourne (answer, tools_used, confidence)."""
    tools_used = [r["name"] for r in tool_results if r.get("ok")]
    kind = intent.follow_up_kind or rctx.follow_up_kind

    # --- User follow-up depuis mémoire ---
    if intent.name == CopilotIntent.USER_FOLLOWUP:
        idx = intent.ordinal_index if intent.ordinal_index is not None else rctx.ordinal_index
        user = conv.select_user_at(idx) if idx is not None else conv.last_selected_user
        if not user and conv.get_users_list():
            user = conv.get_users_list()[0]
        if not user:
            return (
                "Je n'ai pas d'utilisateur en mémoire. Listez d'abord les utilisateurs actifs.",
                [],
                0.7,
            )
        if kind == "email":
            return format_user_email(user, language=language, ordinal=idx), [], 0.95
        if kind == "role":
            return format_user_role(user, language=language, ordinal=idx), [], 0.95
        return format_user_profile(user, language=language), [], 0.92

    # --- Tracking follow-up ---
    if intent.name in {CopilotIntent.TRACKING_FOLLOWUP, CopilotIntent.TRACKING_NUMBER_EXACT}:
        payload = conv.last_tracking_result or {}
        if tool_results:
            payload = tool_results[0].get("response") or payload
        if kind == "creator":
            return format_tracking_creator(payload, language=language), tools_used, 0.95
        if kind == "delay":
            return format_tracking_delay(payload, language=language), tools_used, 0.94
        if kind == "duration":
            return format_tracking_duration(payload, language=language), tools_used, 0.93
        return format_tracking_for_user(payload, language=language), tools_used, 0.95

    # --- User list / count ---
    if intent.name in {CopilotIntent.USER_LIST, CopilotIntent.LIST_ACTIVE_USERS}:
        payload = tool_results[0]["response"] if tool_results else {}
        users = payload.get("users") or payload.get("admin_accounts") or conv.get_users_list()
        return format_users_list(users, language=language), tools_used, 0.9

    if intent.name in {CopilotIntent.USER_COUNT, CopilotIntent.COUNT_ACTIVE_USERS}:
        payload = tool_results[0]["response"] if tool_results else {}
        if intent.filter_active or intent.name == CopilotIntent.COUNT_ACTIVE_USERS:
            count = payload.get("active")
            if count is None:
                users = payload.get("users") or []
                count = sum(1 for u in users if str(u.get("status", "")).lower() in {"active", "actif"})
            if language == "fr":
                return f"**{count}** utilisateur(s) sont actuellement actifs.", tools_used, 0.92
            return f"**{count}** user(s) are currently active.", tools_used, 0.92
        count = payload.get("count") or payload.get("total") or len(payload.get("users") or [])
        if language == "fr":
            return f"**{count}** utilisateur(s) enregistré(s) sur la plateforme.", tools_used, 0.9
        return f"**{count}** user(s) registered on the platform.", tools_used, 0.9

    if intent.name == CopilotIntent.NOTIFICATION_LIST:
        payload = tool_results[0]["response"] if tool_results else {}
        from app.services.ai_assistant.response_formatter import format_notifications_list
        limit = intent.export_limit
        return format_notifications_list(payload, language=language, limit=limit), tools_used, 0.9

    if intent.name == CopilotIntent.TRACKING_LIST:
        payload = tool_results[0]["response"] if tool_results else {}
        from app.services.ai_assistant.response_formatter import format_tracking_list
        return format_tracking_list(payload, language=language), tools_used, 0.9

    # --- Analytics ---
    if intent.name == CopilotIntent.TOP_ACTIVE_USERS:
        users_p = next((r["response"] for r in tool_results if "user" in r["name"]), {})
        logs_p = next((r["response"] for r in tool_results if "log" in r["name"]), {})
        return format_top_active_users(users_p, logs_p, lang=language), tools_used, 0.9

    if intent.name == CopilotIntent.NOTIFICATION_FREQUENCY:
        notif_p = tool_results[0]["response"] if tool_results else {}
        return format_notification_frequency(notif_p, lang=language), tools_used, 0.91

    if intent.name == CopilotIntent.PLATFORM_HEALTH_REPORT:
        payloads = [{"name": r["name"], "response": r["response"]} for r in tool_results]
        partial = len(tool_results) < 5
        answer = format_platform_health_fast(payloads, lang=language)
        if partial:
            answer += "\n\n*Données partielles disponibles.*"
        return answer, tools_used, 0.88 if not partial else 0.75

    if intent.name == CopilotIntent.SECURITY_REPORT:
        sec = tool_results[0]["response"] if tool_results else {}
        return format_security_report_fast(sec, lang=language), tools_used, 0.87

    if intent.name == CopilotIntent.CRITICAL_INCIDENTS:
        sec = tool_results[0]["response"] if tool_results else {}
        return format_security_for_user(sec, language=language), tools_used, 0.87

    if intent.name == CopilotIntent.SUSPICIOUS_ACTIVITY:
        combined = {}
        for r in tool_results:
            if "suspicious" in r["name"]:
                combined.update(r.get("response") or {})
        return format_suspicious_activity_fast(combined, lang=language), tools_used, 0.86

    if intent.name == CopilotIntent.TICKET_QUERY:
        tk = tool_results[0]["response"] if tool_results else {"status": "error"}
        return format_tickets_for_user(tk, language=language), tools_used, 0.9

    # --- Fallback depuis tool payloads (timeout Gemini) ---
    if tool_results:
        return _answer_from_tool_payloads(tool_results, language=language)

    return "", [], 0.0


def _answer_from_tool_payloads(
    tool_results: list[dict[str, Any]],
    *,
    language: str = "fr",
) -> tuple[str, list[str], float]:
    """Synthèse minimale quand Gemini a échoué mais les outils ont répondu."""
    from app.services.ai_assistant.response_formatter import format_tool_result_for_user

    tools_used = [r["name"] for r in tool_results if r.get("ok")]
    parts: list[str] = []
    for r in tool_results:
        if not r.get("ok"):
            continue
        text = format_tool_result_for_user(
            r.get("response") or {},
            intent="",
            language=language,
            tool_name=r["name"],
        )
        if text and text not in parts:
            parts.append(text)
    if parts:
        return "\n\n".join(parts[:3]), tools_used, 0.82
    return "", tools_used, 0.0


def try_answer_from_tools_on_timeout(
    message: str,
    tool_payloads: list[dict[str, Any]],
    *,
    language: str = "fr",
) -> str | None:
    """Appelé quand Gemini timeout — utilise les données outils déjà collectées."""
    if not tool_payloads:
        return None
    results = [
        {"name": p.get("name", ""), "response": p.get("response") or {}, "ok": True}
        for p in tool_payloads
    ]
    answer, _, conf = _answer_from_tool_payloads(results, language=language)
    return answer if conf >= 0.5 else None
