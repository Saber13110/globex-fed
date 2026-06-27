"""Routes spécialisées admin — tracking précis, sécurité, export, utilisateurs."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole
from app.services.admin_logs_export_service import fetch_activity_logs
from app.services.ai_assistant.entity_memory import (
    EntityMemory,
    build_entity_context_block,
    is_follow_up_message,
    is_tracking_follow_up,
    resolve_message_with_entities,
)
from app.services.ai_assistant.tool_planner import (
    _PLATFORM_HEALTH_REPORT_PATTERN,
    _SECURITY_REPORT_PATTERN,
    _EXECUTIVE_PATTERN,
    _ANALYTICS_PATTERN,
    plan_tools,
)
from app.services.ai_assistant.reasoning_engine import (
    enrich_response_dict,
    is_critical_executive_question,
    plan_critical_tools,
    synthesize_enterprise_response,
)
from app.services.ai_assistant.tool_executor import build_tool_context, execute_enterprise_tool
from app.services.gpt.tool_types import ToolExecutionContext
from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

_SUSPICIOUS_LOG_PATTERN = re.compile(
    r"\b(suspect|suspicious|anomal|inhabitu|intrusion|injection|"
    r"actions?\s+suspectes?|suspicious\s+actions?|security\s+analysis)\b",
    re.I,
)
_ADMIN_USERS_PATTERN = re.compile(
    r"\b(comptes?\s+admin|admin\s+accounts?|liste\s+(?:les\s+)?admins?|"
    r"administrateurs?|admin\s+users?|usuarios?\s+admin|lista\s+(?:los\s+)?usuarios?\s+admin)\b",
    re.I,
)
_EXPORT_LOGS_PATTERN = re.compile(
    r"\b(export|exporter|t[eé]l[eé]charger|download).{0,40}(logs?|journaux|activit).{0,20}(pdf|excel|xlsx)?",
    re.I,
)


def _base_response(
    *,
    reply: str,
    intent: str,
    tool_name: str,
    lang: str,
    tools_used: list[str] | None = None,
    requires_confirmation: bool = False,
    suggested_action: dict[str, Any] | None = None,
    export_preview: dict[str, Any] | None = None,
    export_status: str | None = None,
    confidence: float = 0.92,
    mode: str = "local",
) -> dict[str, Any]:
    return {
        "reply": reply,
        "answer": reply,
        "intent": intent,
        "agent_type": "tracking" if "tracking" in intent else "summary",
        "agent_type_label": "Jarvis",
        "analysis_only": not requires_confirmation,
        "action_executed": False,
        "needs_approval": requires_confirmation,
        "requires_confirmation": requires_confirmation,
        "suggested_action": suggested_action,
        "export_preview": export_preview,
        "export_status": export_status or ("pending" if requires_confirmation else None),
        "llm_provider": mode,
        "llm_degraded": mode == "local_fallback",
        "mode": mode,
        "language": lang,
        "confidence": confidence,
        "tools_used": tools_used or [tool_name],
        "agent_steps": [{"label": tool_name, "status": "done", "detail": None}],
        "agent_reasoning": {
            "objective": intent,
            "plan": [f"Outil : {tool_name}"],
            "action_tool": tool_name,
            "action_label": tool_name,
        },
        "reasoning_summary": f"Données vérifiées via {tool_name}.",
    }


def _merge_entity_state(
    response: dict[str, Any],
    memory: EntityMemory,
    *,
    summary: str | None = None,
) -> dict[str, Any]:
    if summary:
        memory.last_result_summary = summary[:500]
    existing = response.get("copilot_state") or {}
    merged = {**existing, **memory.to_state_updates()}
    response["copilot_state"] = merged
    return response


def _finalize_with_synthesis(
    response: dict[str, Any],
    *,
    message: str,
    lang: str,
    tool_payloads: list[dict[str, Any]],
    memory: EntityMemory,
    intent: str,
) -> dict[str, Any]:
    """Tool output + Gemini → réponse entreprise structurée."""
    entity_ctx = build_entity_context_block(memory)
    synthesis = synthesize_enterprise_response(
        message,
        tool_payloads,
        lang=lang,
        entity_context=entity_ctx,
    )
    enrich_response_dict(response, synthesis, entity_state=memory.to_state_updates())
    response["intent"] = intent
    _merge_entity_state(response, memory, summary=synthesis.reply[:200])
    return response


def _format_tracking_detail(data: dict[str, Any], *, lang: str) -> str:
    tn = data.get("tracking_number") or "—"
    status = data.get("status") or data.get("fedex_status") or "—"
    location = data.get("current_location") or "—"
    updated = (data.get("updated_at") or data.get("created_at") or "—")[:19].replace("T", " ")
    user_name = data.get("user_name") or "—"
    user_email = data.get("user_email") or "—"
    delayed = data.get("is_delayed", False)
    events = data.get("events_count", 0)

    if lang == "en":
        lines = [
            f"## Package {tn}",
            "",
            f"- **Current status:** {status}",
            f"- **Last update:** {updated}",
            f"- **Location:** {location}",
            f"- **Linked user:** {user_name} ({user_email})",
            f"- **Events in history:** {events}",
        ]
        if delayed:
            lines.append("- **Alert:** Delay or exception detected.")
        lines.append("")
        lines.append("**Recommendation:** Verify status with the customer if the package is delayed.")
        return "\n".join(lines)

    lines = [
        f"## Colis {tn}",
        "",
        f"- **Statut actuel :** {status}",
        f"- **Dernière mise à jour :** {updated}",
        f"- **Localisation :** {location}",
        f"- **Utilisateur lié :** {user_name} ({user_email})",
        f"- **Événements dans l'historique :** {events}",
    ]
    if delayed:
        lines.append("- **Alerte :** Retard ou anomalie détectée.")
    lines.append("")
    lines.append("**Recommandation :** Vérifier le statut avec le client si le colis est en retard.")
    return "\n".join(lines)


def _handle_get_tracking_by_number(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    memory: EntityMemory,
) -> dict[str, Any] | None:
    tn = extract_tracking_number(message)
    if not tn and memory.last_tracking_number and (
        is_follow_up_message(message) or is_tracking_follow_up(message, memory)
    ):
        tn = memory.last_tracking_number
    if not tn:
        has_tracking_intent = re.search(
            r"\b(suis|suiv|track|colis|tracking|exp[eé]d|ship|num[eé]ro|8813)\b", message, re.I,
        ) or re.search(r"\d{10,}", message)
        if not has_tracking_intent and not is_follow_up_message(message):
            return None
        if is_follow_up_message(message) and memory.last_tracking_number:
            tn = memory.last_tracking_number
    if not tn:
        return None

    ctx = build_tool_context(db, admin, ui_language=lang)
    item = execute_enterprise_tool(ctx, "get_tracking_by_number", {"tracking_number": tn})
    payload = item.get("response") or {}
    tool_payloads = [{"name": "get_tracking_by_number", "response": payload}]

    if payload.get("status") == "error":
        err = payload.get("error") or "Colis introuvable."
        reply = (
            f"Je n'ai pas trouvé le colis **{tn}** en base ni via FedEx.\n\n{err}"
            if lang == "fr"
            else f"Package **{tn}** not found in database or FedEx.\n\n{err}"
        )
        resp = _base_response(
            reply=reply, intent="tracking_lookup", tool_name="get_tracking_by_number",
            lang=lang, confidence=0.85,
        )
        return _merge_entity_state(resp, memory)

    memory.update_from_tool("get_tracking_by_number", payload, intent="tracking_lookup")
    reply = _format_tracking_detail(payload, lang=lang)
    resp = _base_response(
        reply=reply, intent="tracking_lookup", tool_name="get_tracking_by_number",
        lang=lang, confidence=0.94, mode="deterministic",
    )
    from app.services.ai_assistant.conversation_state import ConversationState
    conv = ConversationState.from_copilot_state(resp.get("copilot_state"))
    conv.enrich_from_tool("get_tracking_by_number", payload, intent="tracking_lookup")
    conv.last_language = lang
    merged = conv.merge_into_copilot_state(memory.to_state_updates())
    resp["copilot_state"] = merged
    resp["answer"] = reply
    return resp


def _handle_admin_users_list(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    memory: EntityMemory,
) -> dict[str, Any] | None:
    if not _ADMIN_USERS_PATTERN.search(message):
        return None

    ctx = build_tool_context(db, admin, ui_language=lang)
    item = execute_enterprise_tool(ctx, "get_admin_users", {"limit": 30})
    payload = item.get("response") or {}
    tool_payloads = [{"name": "get_admin_users", "response": payload}]
    memory.update_from_tool("get_admin_users", payload, intent="user_admin_list")

    resp = _base_response(
        reply="", intent="user_admin_list", tool_name="get_admin_users",
        lang=lang, confidence=0.93,
    )
    return _finalize_with_synthesis(
        resp, message=message, lang=lang,
        tool_payloads=tool_payloads, memory=memory, intent="user_admin_list",
    )


def _analyze_suspicious_logs_payload(logs: list, *, hours: int) -> dict[str, Any]:
    suspicious: list[dict[str, str]] = []
    login_failures = 0
    admin_actions = 0
    injection_hits = 0

    for row in logs:
        action = (row.action or "").lower()
        msg = (row.message or "").lower()
        level = (row.level or "").upper()

        if "login" in action and level in {"WARNING", "ERROR"}:
            login_failures += 1
            suspicious.append({
                "type": "login_failure",
                "detail": f"{row.created_at} [{level}] {row.action} — {(row.message or '')[:120]}",
            })
        if "admin" in action or "copilot" in action:
            admin_actions += 1
        if "injection" in msg or "prompt" in msg and "guard" in msg:
            injection_hits += 1
            suspicious.append({
                "type": "injection_attempt",
                "detail": f"{row.created_at} — {(row.message or '')[:120]}",
            })
        if level == "ERROR":
            suspicious.append({
                "type": "error",
                "detail": f"{row.created_at} — {row.action} — {(row.message or '')[:100]}",
            })

    score = len(suspicious)
    if score >= 8 or injection_hits >= 2:
        risk = "élevé"
    elif score >= 3:
        risk = "moyen"
    else:
        risk = "faible"

    return {
        "risk_level": risk,
        "period_hours": hours,
        "total_logs": len(logs),
        "login_failures": login_failures,
        "admin_actions": admin_actions,
        "injection_attempts": injection_hits,
        "suspicious_events": suspicious[:15],
    }


def _format_suspicious_analysis(analysis: dict[str, Any], *, lang: str) -> str:
    risk = analysis.get("risk_level", "faible")
    events = analysis.get("suspicious_events") or []

    if lang == "en":
        lines = [
            "## Security log analysis",
            "",
            f"- **Risk level:** {risk.upper()}",
            f"- **Period:** last {analysis.get('period_hours', 24)}h",
            f"- **Logs analyzed:** {analysis.get('total_logs', 0)}",
            f"- **Login failures:** {analysis.get('login_failures', 0)}",
            f"- **Injection attempts:** {analysis.get('injection_attempts', 0)}",
            "",
            "### Suspicious events",
        ]
    else:
        lines = [
            "## Analyse sécurité des logs",
            "",
            f"- **Niveau de risque :** {risk.upper()}",
            f"- **Période :** {analysis.get('period_hours', 24)} dernières heures",
            f"- **Logs analysés :** {analysis.get('total_logs', 0)}",
            f"- **Échecs de connexion :** {analysis.get('login_failures', 0)}",
            f"- **Tentatives d'injection :** {analysis.get('injection_attempts', 0)}",
            "",
            "### Événements suspects",
        ]

    if not events:
        lines.append(
            "Aucun événement suspect significatif détecté."
            if lang == "fr"
            else "No significant suspicious events detected."
        )
    else:
        for ev in events[:10]:
            lines.append(f"- [{ev.get('type', '?')}] {ev.get('detail', '')}")

    lines.extend([
        "",
        "**Recommandation :** "
        + (
            "Surveiller les tentatives d'injection et renforcer l'authentification admin."
            if risk in {"moyen", "élevé"}
            else "Activité normale — poursuivre la surveillance IDS."
        ) if lang == "fr" else (
            "Monitor injection attempts and strengthen admin authentication."
            if risk in {"moyen", "élevé", "medium", "high"}
            else "Normal activity — continue IDS monitoring."
        ),
    ])
    return "\n".join(lines)


def _handle_suspicious_logs(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    memory: EntityMemory,
) -> dict[str, Any] | None:
    if not _SUSPICIOUS_LOG_PATTERN.search(message):
        return None

    hours = 24
    m = re.search(r"\b(\d{1,3})\s*(?:h|heures?|hours?)\b", message, re.I)
    if m:
        hours = min(int(m.group(1)), 168)

    logs = fetch_activity_logs(db, hours=hours, limit=200)
    analysis = _analyze_suspicious_logs_payload(logs, hours=hours)
    tool_payloads = [{"name": "analyze_suspicious_logs", "response": {"status": "ok", **analysis}}]
    memory.update_from_tool("analyze_suspicious_logs", analysis, intent="security_log_analysis")

    resp = _base_response(
        reply="", intent="security_log_analysis", tool_name="analyze_suspicious_logs",
        lang=lang, confidence=0.91,
    )
    return _finalize_with_synthesis(
        resp, message=message, lang=lang,
        tool_payloads=tool_payloads, memory=memory, intent="security_log_analysis",
    )


def _parse_export_hours(message: str) -> int:
    m = re.search(r"\b(\d{1,3})\s*(?:derni[eè]res?|last)?\s*(?:heures?|hours?|h)\b", message, re.I)
    if m:
        return min(int(m.group(1)), 168)
    if re.search(r"\b24\s*h|\b24h|24\s*heures?\b", message, re.I):
        return 24
    return 24


def _handle_export_request(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
) -> dict[str, Any] | None:
    """Workflow export professionnel — preview + confirmation (sans mode Agent)."""
    from app.services.ai_assistant.export_workflow_service import (
        build_suggested_action,
        detect_export_intent,
        format_preview_reply,
        prepare_export_preview,
    )

    intent = detect_export_intent(message)
    if not intent:
        return None

    preview, err = prepare_export_preview(db, admin, intent, lang=lang)
    if err:
        reply = f"Export impossible : {err}" if lang == "fr" else f"Export denied: {err}"
        return _base_response(
            reply=reply, intent="export_denied", tool_name="export",
            lang=lang, confidence=0.9,
        )
    if not preview:
        return None

    tool_name = f"export_{preview.module}_{preview.fmt}"
    intent_name = f"export_{preview.module}_{preview.fmt}"
    reply = format_preview_reply(preview, lang=lang)

    return _base_response(
        reply=reply,
        intent=intent_name,
        tool_name=tool_name,
        lang=lang,
        requires_confirmation=True,
        suggested_action=build_suggested_action(preview),
        export_preview=preview.to_dict(),
        export_status="pending",
        confidence=0.96,
    )


def _handle_critical_executive(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    memory: EntityMemory,
) -> dict[str, Any] | None:
    if not is_critical_executive_question(message):
        return None

    ctx = build_tool_context(db, admin, ui_language=lang)
    tool_payloads: list[dict[str, Any]] = []
    tools_used: list[str] = []

    for tool_name, args in plan_critical_tools():
        item = execute_enterprise_tool(ctx, tool_name, args)
        tool_payloads.append(item)
        tools_used.append(tool_name)
        resp = item.get("response") or {}
        if resp.get("status") != "error":
            memory.update_from_tool(tool_name, resp, intent="critical_executive")

    resp = _base_response(
        reply="", intent="critical_executive", tool_name="multi_tool",
        lang=lang, tools_used=tools_used, confidence=0.91,
    )
    return _finalize_with_synthesis(
        resp, message=message, lang=lang,
        tool_payloads=tool_payloads, memory=memory, intent="critical_executive",
    )


def _handle_multi_tool_report(
    db: Session,
    admin: User,
    message: str,
    *,
    lang: str,
    memory: EntityMemory,
    intent: str,
) -> dict[str, Any] | None:
    """Rapports multi-outils — santé plateforme, sécurité, exécutif, analytics."""
    planned = plan_tools(message, intent, copilot_state=memory.to_state_updates())
    if len(planned) < 2:
        return None
    ctx = build_tool_context(db, admin, ui_language=lang)
    tool_payloads: list[dict[str, Any]] = []
    tools_used: list[str] = []
    for tool_name, args in planned:
        item = execute_enterprise_tool(ctx, tool_name, args)
        tool_payloads.append(item)
        tools_used.append(tool_name)
        resp = item.get("response") or {}
        if resp.get("status") != "error":
            memory.update_from_tool(tool_name, resp, intent=intent)
    resp = _base_response(
        reply="", intent=intent, tool_name="multi_tool",
        lang=lang, tools_used=tools_used, confidence=0.9,
    )
    return _finalize_with_synthesis(
        resp, message=message, lang=lang,
        tool_payloads=tool_payloads, memory=memory, intent=intent,
    )


def _handle_platform_health_report(
    db: Session, admin: User, message: str, *, lang: str, memory: EntityMemory,
) -> dict[str, Any] | None:
    if not _PLATFORM_HEALTH_REPORT_PATTERN.search(message):
        return None
    return _handle_multi_tool_report(
        db, admin, message, lang=lang, memory=memory, intent="platform_health_report",
    )


def _handle_security_report(
    db: Session, admin: User, message: str, *, lang: str, memory: EntityMemory,
) -> dict[str, Any] | None:
    if not _SECURITY_REPORT_PATTERN.search(message):
        return None
    ctx = build_tool_context(db, admin, ui_language=lang)
    item = execute_enterprise_tool(ctx, "generate_security_report", {})
    payload = item.get("response") or {}
    tool_payloads = [{"name": "generate_security_report", "response": payload}]
    memory.update_from_tool("generate_security_report", payload, intent="security_report")
    resp = _base_response(
        reply="", intent="security_report", tool_name="generate_security_report",
        lang=lang, tools_used=["generate_security_report"],
    )
    return _finalize_with_synthesis(
        resp, message=message, lang=lang,
        tool_payloads=tool_payloads, memory=memory, intent="security_report",
    )


def _handle_executive_or_analytics(
    db: Session, admin: User, message: str, *, lang: str, memory: EntityMemory,
) -> dict[str, Any] | None:
    if _EXECUTIVE_PATTERN.search(message):
        return _handle_multi_tool_report(
            db, admin, message, lang=lang, memory=memory, intent="executive_report",
        )
    if _ANALYTICS_PATTERN.search(message):
        return _handle_multi_tool_report(
            db, admin, message, lang=lang, memory=memory, intent="user_analytics",
        )
    return None


def try_specialized_route(
    db: Session,
    admin: User,
    message: str,
    *,
    agent_mode: bool = False,
    lang: str | None = None,
    copilot_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Route métier précise — prioritaire sur le pipeline générique."""
    from app.services.ai_assistant.language_service import resolve_response_language

    lang, _ = resolve_response_language(
        message,
        session_language=lang,
        profile_language=getattr(admin, "preferred_language", None),
    )
    memory = EntityMemory.from_copilot_state(copilot_state)
    resolved_message, _ = resolve_message_with_entities(message, memory)
    logger.info("[AI] specialized route — lang=%s entity=%s", lang, memory.last_tracking_number)

    for handler in (
        lambda: _handle_platform_health_report(db, admin, resolved_message, lang=lang, memory=memory),
        lambda: _handle_security_report(db, admin, resolved_message, lang=lang, memory=memory),
        lambda: _handle_executive_or_analytics(db, admin, resolved_message, lang=lang, memory=memory),
        lambda: _handle_critical_executive(db, admin, resolved_message, lang=lang, memory=memory),
        lambda: _handle_get_tracking_by_number(db, admin, resolved_message, lang=lang, memory=memory),
        lambda: _handle_export_request(db, admin, message, lang=lang),
        lambda: _handle_suspicious_logs(db, admin, resolved_message, lang=lang, memory=memory),
        lambda: _handle_admin_users_list(db, admin, message, lang=lang, memory=memory),
    ):
        result = handler()
        if result:
            logger.info("[AI] specialized route matched — intent=%s", result.get("intent"))
            if not result.get("copilot_state"):
                _merge_entity_state(result, memory, summary=(result.get("reply") or "")[:200])
            return result
    return None
