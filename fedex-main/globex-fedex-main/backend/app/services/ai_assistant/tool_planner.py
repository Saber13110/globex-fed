"""Planification multi-outils selon intention et type de question."""

from __future__ import annotations

import re
from typing import Any

from app.services.gpt.intent_classifier import (
    INTENT_ADMIN_CONVERSATIONS,
    INTENT_ADMIN_LOGS,
    INTENT_ADMIN_NOTIFICATIONS,
    INTENT_ADMIN_TICKETS,
    INTENT_ADMIN_TRACKING,
    INTENT_ADMIN_USERS,
    INTENT_CAPABILITIES,
    INTENT_KNOWLEDGE,
    classify_intent,
)

SLUG = "fedex-admin-ops"

_ADMIN_USERS_PATTERN = re.compile(
    r"\b(comptes?\s+admin|admin\s+accounts?|liste\s+(?:les\s+)?admins?|"
    r"administrateurs?|admin\s+users?|usuarios?\s+admin|lista\s+(?:los\s+)?usuarios?\s+admin)\b",
    re.I,
)
_SUSPICIOUS_LOGS_PATTERN = re.compile(
    r"\b(suspect|suspicious|anomal|inhabitu|intrusion|injection|"
    r"actions?\s+suspectes?|suspicious\s+actions?)\b",
    re.I,
)
_EXPORT_LOGS_PATTERN = re.compile(
    r"\b(export|exporter|t[eé]l[eé]charger|download).{0,40}(logs?|journaux|activit)",
    re.I,
)
_EXPORT_GENERIC_PATTERN = re.compile(
    r"\b("
    r"export|exporter|t[eé]l[eé]charger|download|envoie|envoyer|"
    r"g[eé]n[eè]re|g[eé]n[eè]rer|g[eé]nere|genere|cr[eé]e|cr[eé]er|fais|"
    r"fichier|document|sous\s+forme|sous\s+form|format\s+pdf|en\s+pdf|excel|xlsx|mettre"
    r")\b",
    re.I,
)
_EXPORT_CORRECTION_PATTERN = re.compile(
    r"\b("
    r"pas\s+24|pas\s+les?\s+24|j'ai\s+dit|jaid\s+dis|corrige|erreur|plut[oô]t|"
    r"dernier\s+\d|derniers?\s+\d|\d+\s*(?:jours?|jour|jr|j)\b"
    r")\b",
    re.I,
)


def _combined_export_text(
    message: str,
    conversation_history: list[dict[str, str]] | None,
) -> str:
    parts: list[str] = [(message or "").strip()]
    for item in reversed(conversation_history or []):
        content = (item.get("content") or "").strip()
        if content:
            parts.append(content)
        if len(parts) >= 4:
            break
    return " ".join(reversed(parts))


def _parse_logs_hours(combined: str) -> int:
    from app.services.admin_logs_export_service import parse_log_period_hours

    t = (combined or "").lower()
    m = (
        re.search(r"(\d+)\s*(?:jours?|jour)\b", t)
        or re.search(r"(\d+)jr\b", t)
        or re.search(r"derniers?\s+(\d+)\s*(?:jours?|jour|jr|j)\b", t)
    )
    if m:
        return min(int(m.group(1)) * 24, 168)
    for hm in re.finditer(r"(\d+)\s*(?:h|heures?)\b", t):
        before = t[max(0, hm.start() - 12): hm.start()]
        if re.search(r"\b(pas|non)\s*$", before):
            continue
        return min(max(int(hm.group(1)), 1), 168)
    return parse_log_period_hours(t, default=24)


def _logs_export_args(
    message: str,
    conversation_history: list[dict[str, str]] | None,
    *,
    export_fmt: str = "pdf",
) -> list[tuple[str, dict[str, Any]]]:
    from app.services.gpt.copilot_conversation_state import parse_limit_from_message

    combined = _combined_export_text(message, conversation_history)
    hours = _parse_logs_hours(combined)
    limit = min(max(int(parse_limit_from_message(combined, default=500) or 500), 1), 500)
    tool = "export_activity_logs_excel" if export_fmt == "xlsx" else "export_activity_logs_pdf"
    return [(tool, {"hours": hours, "limit": limit})]


def _plan_export_correction(
    message: str,
    conversation_history: list[dict[str, str]] | None,
) -> list[tuple[str, dict[str, Any]]] | None:
    """Relance export après correction (« j'ai dit 5 jours pas 24h »)."""
    text = message or ""
    if not _EXPORT_CORRECTION_PATTERN.search(text):
        return None
    combined = _combined_export_text(text, conversation_history).lower()
    if not (
        re.search(r"\blogs?\b", combined, re.I)
        or "activity-logs" in combined
        or "export_activity_logs" in combined
    ):
        return None
    from app.services.gpt.copilot_conversation_state import detect_export_format

    export_fmt = detect_export_format(text) or detect_export_format(combined) or "pdf"
    return _logs_export_args(text, conversation_history, export_fmt=export_fmt or "pdf")

_CRITICAL_PATTERN = re.compile(
    r"\b(critique|probl[eè]me|probleme|problem|issue|sant[eé]|sante|health|priorit|"
    r"urgent|alerte|alert|dysfonction|anomal)\b",
    re.I,
)
_SECURITY_PATTERN = re.compile(
    r"\b(s[eé]curit[eé]|security|ids|intrusion|incident[s]?\s+s[eé]curit|"
    r"security\s+incident|alertes?\s+s[eé]curit)\b",
    re.I,
)
_HEALTH_PATTERN = re.compile(
    r"\b(syst[eè]me semble|platform health|sant[eé] plateforme|"
    r"état global|etat global|everything ok|system ok)\b",
    re.I,
)
_PLATFORM_HEALTH_REPORT_PATTERN = re.compile(
    r"\b("
    r"rapport.{0,40}(sant[eé]|plateforme)|"
    r"sant[eé].{0,25}(plateforme|compl[eè]t|complet)|"
    r"bilan plateforme|r[eé]sum[eé] plateforme|[eé]tat plateforme|"
    r"rapport complet de sant[eé]"
    r")\b",
    re.I,
)
_SECURITY_REPORT_PATTERN = re.compile(
    r"\b(rapport.{0,30}s[eé]curit[eé]|security report|rapport s[eé]curit[eé] complet)\b",
    re.I,
)
_ANALYTICS_PATTERN = re.compile(
    r"\b("
    r"plus actif|top utilisateur|utilisateurs?.{0,20}activit[eé]|"
    r"plus de tracking|plus de tickets?|plus de notifications?|"
    r"g[eé]n[eè]re.{0,20}activit[eé]|classement"
    r")\b",
    re.I,
)
_EXECUTIVE_PATTERN = re.compile(
    r"\b("
    r"rapport ex[eé]cutif|r[eé]sum[eé] global|kpi important|incidents majeurs|"
    r"surveiller aujourd|activit[eé] d.?aujourd|que doit surveiller|"
    r"pr[eé]pare un rapport|r[eé]sum[eé] de la plateforme"
    r")\b",
    re.I,
)
_TRACKING_FOLLOWUP_PATTERN = re.compile(
    r"\b(o[uù]\s+est|where\s+is|statut|exp[eé]diteur|exporte.?le|maintenant|son historique)\b",
    re.I,
)
_WEEKLY_PATTERN = re.compile(
    r"\b(semaine|weekly|week|7 jours|7 days|cette semaine|this week)\b",
    re.I,
)

_INTENT_TOOLS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    INTENT_ADMIN_TRACKING: [
        ("get_tracking_summary", {"limit": 30}),
    ],
    INTENT_ADMIN_NOTIFICATIONS: [
        ("get_notifications_summary", {"limit": 20}),
    ],
    INTENT_ADMIN_USERS: [
        ("get_users_summary", {"limit": 50}),
    ],
    INTENT_ADMIN_LOGS: [
        ("get_recent_logs", {"hours": 24, "limit": 40}),
    ],
    INTENT_ADMIN_TICKETS: [
        ("get_open_tickets", {"status": "open", "limit": 30}),
    ],
    INTENT_ADMIN_CONVERSATIONS: [
        ("get_conversations_summary", {"limit": 40}),
    ],
    INTENT_KNOWLEDGE: [
        ("search_knowledge_base", {"limit": 8}),
    ],
}

_CRITICAL_PLAN: list[tuple[str, dict[str, Any]]] = [
    ("get_recent_logs", {"hours": 48, "limit": 40}),
    ("get_security_alerts", {}),
    ("get_notifications_summary", {"limit": 15, "critical_only": True}),
    ("get_open_tickets", {"status": "open", "limit": 20}),
    ("get_tracking_summary", {"limit": 20}),
    ("analyze_platform_health", {}),
]

_PLATFORM_HEALTH_PLAN: list[tuple[str, dict[str, Any]]] = [
    ("get_platform_stats", {}),
    ("get_tracking_summary", {"limit": 20}),
    ("get_users_summary", {"limit": 30}),
    ("get_open_tickets", {"status": "open", "limit": 20}),
    ("get_notifications_summary", {"limit": 20}),
    ("get_security_alerts", {"status": "open", "limit": 15}),
]

_SECURITY_REPORT_PLAN: list[tuple[str, dict[str, Any]]] = [
    ("generate_security_report", {}),
]

_ANALYTICS_USERS_PLAN: list[tuple[str, dict[str, Any]]] = [
    ("get_users_summary", {"limit": 50}),
    ("get_recent_logs", {"hours": 24, "limit": 50}),
]

_EXECUTIVE_PLAN: list[tuple[str, dict[str, Any]]] = [
    ("get_platform_stats", {}),
    ("get_security_alerts", {"status": "open", "limit": 15}),
    ("get_open_tickets", {"status": "open", "limit": 15}),
    ("get_notifications_summary", {"limit": 15, "critical_only": True}),
    ("get_tracking_summary", {"limit": 15}),
    ("get_recent_logs", {"hours": 24, "limit": 30}),
]


def _extract_custom_pdf_text(message: str) -> str | None:
    from app.utils.pdf_text_extract import extract_custom_pdf_text

    return extract_custom_pdf_text(message)


def _plan_custom_text_pdf(message: str) -> list[tuple[str, dict[str, Any]]] | None:
    """PDF texte libre — sans module DB (ex. génère un pdf avec bonjour)."""
    from app.services.gpt.copilot_conversation_state import infer_module_from_message

    text = message or ""
    if not re.search(r"\bpdf\b", text, re.I):
        return None
    if _EXPORT_LOGS_PATTERN.search(text) or infer_module_from_message(text):
        return None
    body = _extract_custom_pdf_text(text)
    if not body:
        return None
    return [("generate_text_pdf", {"text": body})]


_FORMAT_SWITCH_RE = re.compile(
    r"\b(excel|xlsx|pdf|sous\s+form|sous\s+forme|format|pardon|plut[oô]t|je\s+veux)\b",
    re.I,
)


def _plan_format_switch(
    message: str,
    conversation_history: list[dict[str, str]] | None,
) -> list[tuple[str, dict[str, Any]]] | None:
    """Relance export en changeant le format (ex. PDF → Excel)."""
    from app.services.ai_assistant.export_pipeline import export_tool_name
    from app.services.gpt.copilot_conversation_state import (
        detect_export_format,
        infer_last_export_from_history,
        infer_module_from_message,
        parse_limit_from_message,
    )

    text = message or ""
    export_fmt = detect_export_format(text)
    if not export_fmt or not _FORMAT_SWITCH_RE.search(text):
        return None
    if infer_module_from_message(text):
        return None

    mod, limit, _prev_fmt = infer_last_export_from_history(conversation_history)
    if not mod:
        return None

    if mod == "logs":
        return _logs_export_args(text, conversation_history, export_fmt=export_fmt)

    limit = limit or parse_limit_from_message(_combined_export_text(text, conversation_history), default=20) or 20
    tool = export_tool_name(mod, export_fmt)
    return [(tool, {"limit": min(max(int(limit), 1), 100), "module": mod, "format": export_fmt})]


def plan_export_tools(
    message: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> list[tuple[str, dict[str, Any]]] | None:
    """Si la demande vise un export fichier, retourne l'outil PDF/XLSX adapté."""
    from app.services.ai_assistant.export_pipeline import export_tool_name
    from app.services.globex_agent.client_action_planner import is_client_communication_action
    from app.services.gpt.copilot_conversation_state import (
        detect_export_format,
        infer_module_from_message,
        merge_conversation_state,
        parse_limit_from_message,
        resolve_copilot_turn,
    )

    text = message or ""
    if is_client_communication_action(text):
        return None
    history = conversation_history or []

    custom_pdf = _plan_custom_text_pdf(text)
    if custom_pdf:
        return custom_pdf

    correction = _plan_export_correction(text, history)
    if correction:
        return correction

    format_switch = _plan_format_switch(text, history)
    if format_switch:
        return format_switch

    state = merge_conversation_state(None, history)
    resolved = resolve_copilot_turn(text, state, messages=history)
    if resolved.kind == "contextual_export" and resolved.module:
        module = resolved.module
        limit = min(max(int(resolved.limit or 20), 1), 100)
        export_fmt = resolved.export_format or "pdf"
        if module == "logs":
            from app.services.gpt.copilot_conversation_state import detect_export_format as _det_fmt

            fmt = export_fmt or _det_fmt(text) or "pdf"
            return _logs_export_args(text, history, export_fmt=fmt or "pdf")
        tool = export_tool_name(module, export_fmt or "pdf")
        return [(tool, {"limit": limit, "module": module, "format": export_fmt or "pdf"})]

    export_fmt = detect_export_format(text)
    if not export_fmt and not _EXPORT_GENERIC_PATTERN.search(text):
        return None

    module = infer_module_from_message(text)
    if not module:
        if _EXPORT_LOGS_PATTERN.search(text) or re.search(r"\blogs?\b", text, re.I):
            module = "logs"
        else:
            return _plan_custom_text_pdf(text)
    if module in {"security", "knowledge", "reports"}:
        return None

    limit = parse_limit_from_message(text, default=20) or 20

    if module == "logs":
        return _logs_export_args(text, history, export_fmt=export_fmt or "pdf")

    tool = export_tool_name(module, export_fmt or "pdf")
    return [(tool, {"limit": min(max(limit, 1), 100), "module": module, "format": export_fmt or "pdf"})]


def plan_tools(
    message: str,
    intent: str,
    copilot_state: dict[str, Any] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Sélectionne les outils à exécuter avant synthèse LLM."""
    from app.services.ai_assistant.entity_memory import EntityMemory, is_tracking_follow_up
    from app.services.llm.tracking_extract import extract_tracking_number

    text = message or ""
    memory = EntityMemory.from_copilot_state(copilot_state)

    from app.services.globex_agent.client_action_planner import plan_client_action_tools

    client_planned = plan_client_action_tools(text)
    if client_planned:
        return client_planned

    export_planned = plan_export_tools(text, conversation_history)
    if export_planned:
        return export_planned

    tn = extract_tracking_number(text)
    if tn:
        return [("get_tracking_by_number", {"tracking_number": tn})]

    # Relance colis mémorisé — priorité absolue
    if memory.last_tracking_number and (
        is_tracking_follow_up(text, memory) or _TRACKING_FOLLOWUP_PATTERN.search(text)
    ):
        return [("get_tracking_by_number", {"tracking_number": memory.last_tracking_number})]

    if _ADMIN_USERS_PATTERN.search(text):
        return [("get_admin_users", {"limit": 30})]

    # Rapports structurés — avant _CRITICAL_PATTERN (évite confusion « santé »)
    if _PLATFORM_HEALTH_REPORT_PATTERN.search(text):
        return list(_PLATFORM_HEALTH_PLAN)

    if _SECURITY_REPORT_PATTERN.search(text):
        return list(_SECURITY_REPORT_PLAN)

    if _EXECUTIVE_PATTERN.search(text):
        return list(_EXECUTIVE_PLAN)

    if _ANALYTICS_PATTERN.search(text):
        return list(_ANALYTICS_USERS_PLAN)

    if _SUSPICIOUS_LOGS_PATTERN.search(text):
        return [("analyze_suspicious_logs", {"hours": 24})]

    if _EXPORT_LOGS_PATTERN.search(text):
        return []  # géré par specialized_routes (confirmation mode Agent)

    # Sécurité AVANT le plan critique
    if _SECURITY_PATTERN.search(text):
        status = "open" if re.search(r"\b(ouvert|open|actif)\b", text, re.I) else "open"
        return [("get_security_alerts", {"status": status, "limit": 20})]

    if _CRITICAL_PATTERN.search(text):
        return list(_CRITICAL_PLAN)

    if _HEALTH_PATTERN.search(text):
        return [("analyze_platform_health", {})]

    if _WEEKLY_PATTERN.search(text):
        return [("analyze_weekly_activity", {"hours": 168})]

    if intent == INTENT_CAPABILITIES:
        return []

    planned = _INTENT_TOOLS.get(intent, [])
    if planned:
        return list(planned)

    # Questions KPI / dashboard
    if re.search(r"\b(r[eé]sum[eé]|summary|kpi|plateforme|platform|dashboard|statist)\b", text, re.I):
        return [("get_platform_stats", {})]

    if re.search(r"\b(s[eé]curit[eé]|security|ids|intrusion|alerte)\b", text, re.I):
        return [("get_security_alerts", {"status": "open", "limit": 20})]

    if re.search(r"\b(mission|missions|agent mission)\b", text, re.I):
        return [("get_agent_missions_summary", {"limit": 20})]

    if re.search(r"\b(rapport|report|export)\b", text, re.I):
        return [("get_reports_summary", {})]

    classification = classify_intent(text, SLUG)
    return list(_INTENT_TOOLS.get(classification.intent, []))
