"""Classification d'intention par priorité — ordre strict."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.ai_assistant.context_resolver import ResolvedContext, resolve_context
from app.services.ai_assistant.conversation_state import ConversationState
from app.services.ai_assistant.entity_memory import EntityMemory, is_contextual_reference
from app.services.llm.tracking_extract import extract_tracking_number

_PLATFORM_HEALTH_RE = re.compile(
    r"\b("
    r"rapport.{0,40}(sant[eé]|plateforme)|"
    r"sant[eé].{0,25}(plateforme|compl[eè]t|globex)|"
    r"bilan plateforme|r[eé]sum[eé] global plateforme|[eé]tat global plateforme|"
    r"rapport complet de sant[eé]"
    r")\b",
    re.I,
)
_SECURITY_REPORT_RE = re.compile(
    r"\b(rapport.{0,30}s[eé]curit[eé]|security report|rapport de s[eé]curit[eé] complet)\b",
    re.I,
)
_SECURITY_CRITICAL_RE = re.compile(
    r"\b(incidents?\s+critiques?|critical\s+incidents?|quels incidents sont critiques)\b",
    re.I,
)
_SUSPICIOUS_RE = re.compile(
    r"\b(suspect|suspicious|anomal|inhabitu|activit[eé]s?\s+suspectes?|"
    r"actions?\s+anormales?|intrusion|injection)\b",
    re.I,
)
_TOP_ACTIVE_RE = re.compile(
    r"\b(plus actif|top utilisateur|utilisateurs?.{0,25}activit[eé]|g[eé]n[eè]rent le plus)\b",
    re.I,
)
_NOTIF_FREQ_RE = re.compile(
    r"\b(types? de notifications?.{0,20}fr[eé]quent|quels types de notifications)\b",
    re.I,
)
_TICKETS_RE = re.compile(r"\b(tickets?\s+ouverts?|open tickets?|quels tickets)\b", re.I)
_EXPORT_RE = re.compile(r"\b(export|exporte|pdf|xlsx|t[eé]l[eé]charge)\b", re.I)
_GREETING_RE = re.compile(r"^\s*(bonjour|salut|hello|hi|hey|hola|coucou|bonsoir)\b", re.I)


@dataclass
class PriorityIntent:
    name: str
    action: str = "ANALYZE"
    domain: str = "generic"
    tracking_number: str | None = None
    is_export: bool = False
    is_contextual: bool = False
    follow_up_kind: str = "none"
    export_limit: int | None = None


def classify_priority_intent(
    message: str,
    *,
    memory: EntityMemory | None = None,
    copilot_state: dict[str, Any] | None = None,
    resolved_ctx: ResolvedContext | None = None,
) -> PriorityIntent:
    """
    Ordre obligatoire :
    1 tracking exact → 2 follow-up → 3 export contextuel → 4 platform_health →
    5 security_report → 6 suspicious → 7 top_active → 8 notif_freq →
    9 tickets → 10-11 users/notifications → 12 greeting
    """
    text = (message or "").strip()
    mem = memory or EntityMemory.from_copilot_state(copilot_state)
    conv = ConversationState.from_copilot_state(copilot_state)
    if memory and memory.last_tracking_number and not conv.last_tracking_number:
        conv.last_tracking_number = memory.last_tracking_number
    ctx = resolved_ctx or resolve_context(text, conv=conv, memory=mem, language=(conv.last_language or "fr"))

    if len(text.split()) <= 4 and _GREETING_RE.match(text):
        return PriorityIntent(name="greeting", action="GREETING")

    # 1. tracking exact (numéro explicite dans le message uniquement)
    explicit_tn = extract_tracking_number(text)
    if explicit_tn and not ctx.is_contextual:
        if _EXPORT_RE.search(text):
            return PriorityIntent(name="export_tracking_history", action="EXPORT", domain="tracking", tracking_number=explicit_tn, is_export=True)
        return PriorityIntent(name="track_by_number", action="TRACK", domain="tracking", tracking_number=explicit_tn)

    # 2. follow-up contextuel tracking
    if ctx.tracking_number and ctx.subject_type == "tracking":
        kind = ctx.follow_up_kind
        if ctx.is_export or kind == "history_export":
            return PriorityIntent(
                name="export_tracking_history", action="EXPORT", domain="tracking",
                tracking_number=ctx.tracking_number, is_export=True, is_contextual=True,
                follow_up_kind=kind,
            )
        return PriorityIntent(
            name="tracking_followup", action="TRACK", domain="tracking",
            tracking_number=ctx.tracking_number, is_contextual=True,
            follow_up_kind=kind,
        )

    # 3. export contextuel (users/notifications avec limite)
    if ctx.is_export or (_EXPORT_RE.search(text) and (is_contextual_reference(text) or ctx.export_limit)):
        if _PLATFORM_HEALTH_RE.search(text):
            pass  # jamais export
        elif ctx.subject_type in {"users", "notifications", "tickets", "tracking"} or mem.has_exportable_context():
            return PriorityIntent(
                name="export_current_context", action="EXPORT",
                domain=ctx.subject_type or mem.last_module or "generic",
                is_export=True, is_contextual=True,
                export_limit=ctx.export_limit,
                tracking_number=ctx.tracking_number,
            )

    # 4. platform health
    if _PLATFORM_HEALTH_RE.search(text):
        return PriorityIntent(name="platform_health_report", action="REPORT", domain="reports")

    # 5. security report
    if _SECURITY_REPORT_RE.search(text):
        return PriorityIntent(name="security_report", action="SECURITY", domain="security")

    # 5b. security critical
    if _SECURITY_CRITICAL_RE.search(text):
        return PriorityIntent(name="security_critical_incidents", action="SECURITY", domain="security")

    # 6. suspicious
    if _SUSPICIOUS_RE.search(text):
        return PriorityIntent(name="suspicious_activity", action="SECURITY", domain="logs")

    # 7. top active
    if _TOP_ACTIVE_RE.search(text):
        return PriorityIntent(name="top_active_users", action="ANALYZE", domain="users")

    # 8. notification frequency
    if _NOTIF_FREQ_RE.search(text):
        return PriorityIntent(name="notification_frequency_analysis", action="ANALYZE", domain="notifications")

    # 9. tickets
    if _TICKETS_RE.search(text):
        return PriorityIntent(name="open_tickets", action="LIST", domain="tickets")

    # 10-11. fallback v2
    from app.services.ai_assistant.intent_router_v2 import classify_intent_v2
    v2 = classify_intent_v2(text, memory=mem)
    return PriorityIntent(
        name=v2.specific_intent,
        action=v2.action,
        domain=v2.domain,
        is_contextual=v2.is_contextual_reference,
        export_limit=ctx.export_limit,
    )
