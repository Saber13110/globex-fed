"""
Classification d'intention v2 — ordre de priorité strict.
Ne traite pas toutes les questions comme admin_query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.services.ai_assistant.context_resolver import ResolvedContext, resolve_context
from app.services.ai_assistant.conversation_state import ConversationState
from app.services.ai_assistant.entity_memory import EntityMemory, is_contextual_reference
from app.services.ai_assistant.export_normalize import parse_export_limit
from app.services.llm.tracking_extract import extract_tracking_number

_PLATFORM_HEALTH_RE = re.compile(
    r"\b(rapport.{0,40}(sant[eé]|plateforme)|sant[eé].{0,25}(plateforme|compl[eè]t)|"
    r"rapport complet de sant[eé]|bilan plateforme)\b",
    re.I,
)
_SECURITY_REPORT_RE = re.compile(r"\b(rapport.{0,30}s[eé]curit[eé]|rapport de s[eé]curit[eé] complet)\b", re.I)
_CRITICAL_RE = re.compile(r"\b(incidents?\s+critiques?|critical\s+incidents?|quels incidents sont critiques)\b", re.I)
_SUSPICIOUS_RE = re.compile(
    r"\b(suspects?|suspectes?|suspicious|actions?\s+suspectes?|activit[eé]s?\s+suspectes?|anomal)\b",
    re.I,
)
_LOGS_SUSPICIOUS_RE = re.compile(
    r"\blogs\b.*\b(suspect|anomal|inhabitu)\b|\b(suspect|anomal|inhabitu)\b.*\blogs\b",
    re.I,
)
_SECURITY_OPEN_RE = re.compile(
    r"\b(incidents?\s+(de\s+)?s[eé]curit[eé]|s[eé]curit[eé].{0,25}ouverts?|incidents?\s+ouverts?)\b",
    re.I,
)
_PROBLEMS_RE = re.compile(
    r"\b(principaux?\s+probl[eè]mes?|probl[eè]mes?\s+actuels?|enjeux?\s+critiques?)\b",
    re.I,
)
_TOP_ACTIVE_RE = re.compile(r"\b(plus actif|top utilisateur|g[eé]n[eè]rent le plus|activit[eé])\b", re.I)
_NOTIF_FREQ_RE = re.compile(r"\b(types? de notifications?.{0,20}fr[eé]quent|quels types de notifications)\b", re.I)
_TICKETS_RE = re.compile(r"\b(tickets?\s+ouverts?|quels tickets)\b", re.I)
_USER_LIST_RE = re.compile(
    r"\b(montre|liste|donne|affiche|voir).{0,30}(utilisateurs?|users?|comptes?)\b", re.I,
)
_USER_COUNT_RE = re.compile(r"\b(combien).{0,20}(utilisateurs?|users?)\b", re.I)
_NOTIF_LIST_RE = re.compile(r"\b(montre|liste|donne).{0,30}(notifs?|notifications?)\b", re.I)
_TRACK_LIST_RE = re.compile(r"\b(montre|liste|derniers?).{0,30}(colis|tracking|exp[eé]ditions?)\b", re.I)
_AGENT_CATALOG_RE = re.compile(r"\b(agents?\s+(pr[eé]sents?|disponibles?)|quels agents|catalogue agents)\b", re.I)
_TOOL_CATALOG_RE = re.compile(r"\b(outils?\s+(disponibles?|pr[eé]sents?)|quels outils|tools catalog)\b", re.I)
_GREETING_RE = re.compile(r"^\s*(bonjour|salut|hello|hi|hey|hola|coucou|bonsoir)\b", re.I)
_EXPORT_RE = re.compile(r"\b(export|exporte|pdf|xlsx|t[eé]l[eé]charge)\b", re.I)
_ACTIVE_USERS_RE = re.compile(r"\butilisateurs?\s+actifs?\b", re.I)
_XLSX_RE = re.compile(r"\b(excel|xlsx|fichier|tableur)\b", re.I)
_SUSPENDABLE_RE = re.compile(
    r"\b(suspendables?|qu.?on\s+peut\s+suspendre|peut.?on\s+suspendre|"
    r"comptes?\s+à\s+surveiller|à\s+surveiller|surveiller)\b",
    re.I,
)
_SUSPENDED_RE = re.compile(r"\b(suspendu[s]?|suspended)\b", re.I)
_TOP_ISSUES_RE = re.compile(
    r"\b((\d+\s+)?probl[eè]mes?\s+.{0,30}critiques?|"
    r"probl[eè]mes?\s+les\s+plus\s+critiques|"
    r"probl[eè]mes?\s+actuels|"
    r"rapport\s+.{0,25}probl[eè]mes?\s+actuels|"
    r"g[eé]n[eè]re\s+un\s+rapport\s+des?\s+probl[eè]mes?)\b",
    re.I,
)
_SECURITY_ALERTS_RE = re.compile(r"\b(alertes?\s+s[eé]curit[eé]|alertes?\s+s[eé]curit[eé])\b", re.I)
_OPEN_INCIDENTS_RE = re.compile(r"\b(incidents?\s+ouverts?|montre.?moi\s+les\s+incidents)\b", re.I)
_CRITICAL_TICKETS_RE = re.compile(r"\b(tickets?\s+critiques?)\b", re.I)
_FOURNIS_RE = re.compile(r"\b(fournis|fournir|donne.?moi)\b", re.I)


class CopilotIntent(str, Enum):
    TRACKING_NUMBER_EXACT = "tracking_number_exact"
    TRACKING_FOLLOWUP = "tracking_followup"
    USER_FOLLOWUP = "user_followup"
    EXPORT_CONTEXTUAL = "export_contextual"
    PLATFORM_HEALTH_REPORT = "platform_health_report"
    SECURITY_REPORT = "security_report"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    CRITICAL_INCIDENTS = "critical_incidents"
    TOP_ACTIVE_USERS = "top_active_users"
    NOTIFICATION_FREQUENCY = "notification_frequency"
    TICKET_QUERY = "ticket_query"
    USER_LIST = "user_list"
    LIST_ACTIVE_USERS = "list_active_users"
    USER_COUNT = "user_count"
    COUNT_ACTIVE_USERS = "count_active_users"
    NOTIFICATION_LIST = "notification_list"
    TRACKING_LIST = "tracking_list"
    AGENT_CATALOG = "agent_catalog"
    TOOL_CATALOG = "tool_catalog"
    GREETING = "greeting"
    UNKNOWN = "unknown"
    TOP_PLATFORM_ISSUES = "top_platform_issues"
    LIST_SUSPENDED_USERS = "list_suspended_users"
    EXPORT_SUSPENDED_USERS = "export_suspended_users"
    LIST_SUSPENDABLE_USERS = "list_suspendable_users"
    EXPORT_SUSPENDABLE_USERS = "export_suspendable_users"
    SECURITY_ALERTS = "security_alerts"
    OPEN_INCIDENTS = "open_incidents"
    CRITICAL_TICKETS = "critical_tickets"


@dataclass
class ClassifiedIntent:
    name: CopilotIntent
    tracking_number: str | None = None
    export_limit: int | None = None
    follow_up_kind: str = "none"
    ordinal_index: int | None = None
    is_contextual: bool = False
    is_export: bool = False
    use_memory_only: bool = False
    domain: str = "generic"
    filter_active: bool = False


def _wants_active_users(text: str) -> bool:
    return bool(re.search(r"\b(actifs?|active)\b", text, re.I))


def _is_suspicious_query(text: str) -> bool:
    return bool(_SUSPICIOUS_RE.search(text) or _LOGS_SUSPICIOUS_RE.search(text))


def classify_copilot_intent(
    message: str,
    *,
    conv: ConversationState | None = None,
    memory: EntityMemory | None = None,
    copilot_state: dict[str, Any] | None = None,
    resolved_ctx: ResolvedContext | None = None,
) -> ClassifiedIntent:
    text = (message or "").strip()
    state = conv or ConversationState.from_copilot_state(copilot_state)
    mem = memory or EntityMemory.from_copilot_state(copilot_state)
    if mem.last_tracking_number and not state.last_tracking_number:
        state.last_tracking_number = mem.last_tracking_number
    ctx = resolved_ctx or resolve_context(text, conv=state, memory=mem, language=state.last_language)

    if len(text.split()) <= 4 and _GREETING_RE.match(text):
        return ClassifiedIntent(name=CopilotIntent.GREETING)

    # 1. tracking exact
    explicit_tn = extract_tracking_number(text)
    if explicit_tn and not ctx.is_contextual:
        if _EXPORT_RE.search(text):
            return ClassifiedIntent(
                name=CopilotIntent.EXPORT_CONTEXTUAL, tracking_number=explicit_tn,
                is_export=True, follow_up_kind="history_export", domain="tracking",
            )
        return ClassifiedIntent(name=CopilotIntent.TRACKING_NUMBER_EXACT, tracking_number=explicit_tn, domain="tracking")

    # 2. tracking follow-up
    if ctx.tracking_number and ctx.subject_type == "tracking":
        if ctx.is_export or ctx.follow_up_kind == "history_export":
            return ClassifiedIntent(
                name=CopilotIntent.EXPORT_CONTEXTUAL, tracking_number=ctx.tracking_number,
                is_export=True, is_contextual=True, follow_up_kind=ctx.follow_up_kind,
                use_memory_only=ctx.use_memory_only, domain="tracking",
            )
        return ClassifiedIntent(
            name=CopilotIntent.TRACKING_FOLLOWUP, tracking_number=ctx.tracking_number,
            is_contextual=True, follow_up_kind=ctx.follow_up_kind,
            use_memory_only=ctx.use_memory_only, domain="tracking",
        )

    # 3. user follow-up (mémoire obligatoire)
    if ctx.subject_type == "users" and ctx.follow_up_kind in {"role", "email", "profile"}:
        return ClassifiedIntent(
            name=CopilotIntent.USER_FOLLOWUP if ctx.follow_up_kind != "profile" else CopilotIntent.EXPORT_CONTEXTUAL,
            is_contextual=True, follow_up_kind=ctx.follow_up_kind,
            ordinal_index=ctx.ordinal_index, is_export=ctx.follow_up_kind == "profile",
            domain="users",
        )

    # 3b. analytics / sécurité — AVANT export contextuel
    if _TOP_ISSUES_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.TOP_PLATFORM_ISSUES, domain="reports")
    if _PLATFORM_HEALTH_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.PLATFORM_HEALTH_REPORT, domain="reports")
    if _SECURITY_REPORT_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.SECURITY_REPORT, domain="security")
    if _is_suspicious_query(text):
        return ClassifiedIntent(name=CopilotIntent.SUSPICIOUS_ACTIVITY, domain="logs")
    if _SECURITY_ALERTS_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.SECURITY_ALERTS, domain="security")
    if _OPEN_INCIDENTS_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.OPEN_INCIDENTS, domain="security")
    if _CRITICAL_TICKETS_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.CRITICAL_TICKETS, domain="tickets")
    if _CRITICAL_RE.search(text) or _SECURITY_OPEN_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.CRITICAL_INCIDENTS, domain="security")
    if _PROBLEMS_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.TOP_PLATFORM_ISSUES, domain="reports")
    if _TOP_ACTIVE_RE.search(text) and re.search(r"\butilisateur", text, re.I):
        return ClassifiedIntent(name=CopilotIntent.TOP_ACTIVE_USERS, domain="users")
    if _NOTIF_FREQ_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.NOTIFICATION_FREQUENCY, domain="notifications")
    if _TICKETS_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.TICKET_QUERY, domain="tickets")

    # Comptes suspendables / à surveiller — AVANT suspendus
    if _SUSPENDABLE_RE.search(text):
        wants_export = bool(_EXPORT_RE.search(text) or _XLSX_RE.search(text) or _FOURNIS_RE.search(text))
        if wants_export:
            return ClassifiedIntent(
                name=CopilotIntent.EXPORT_SUSPENDABLE_USERS, domain="users",
                is_export=True,
            )
        return ClassifiedIntent(name=CopilotIntent.LIST_SUSPENDABLE_USERS, domain="users")

    # Comptes suspendus — list / export (avant export contextuel générique)
    if _SUSPENDED_RE.search(text):
        wants_export = bool(_EXPORT_RE.search(text) or _XLSX_RE.search(text) or _FOURNIS_RE.search(text))
        if wants_export:
            return ClassifiedIntent(
                name=CopilotIntent.EXPORT_SUSPENDED_USERS, domain="users",
                is_export=True, filter_active=False,
            )
        return ClassifiedIntent(name=CopilotIntent.LIST_SUSPENDED_USERS, domain="users")

    # 4. export contextuel
    export_limit = ctx.export_limit or parse_export_limit(text)
    if ctx.is_export or (_EXPORT_RE.search(text) and (is_contextual_reference(text) or export_limit)):
        if not _PLATFORM_HEALTH_RE.search(text):
            return ClassifiedIntent(
                name=CopilotIntent.EXPORT_CONTEXTUAL, is_export=True, is_contextual=True,
                export_limit=export_limit, tracking_number=ctx.tracking_number,
                domain=ctx.subject_type or mem.last_module or "generic",
            )

    # 5–18 listes & catalogues
    active = _wants_active_users(text)
    if _USER_COUNT_RE.search(text):
        name = CopilotIntent.COUNT_ACTIVE_USERS if active else CopilotIntent.USER_COUNT
        return ClassifiedIntent(name=name, domain="users", filter_active=active)
    if _USER_LIST_RE.search(text) or (active and re.search(r"\butilisateur", text, re.I)):
        name = CopilotIntent.LIST_ACTIVE_USERS if active else CopilotIntent.USER_LIST
        return ClassifiedIntent(name=name, domain="users", filter_active=active)
    if _NOTIF_LIST_RE.search(text) or re.search(r"\b(\d+)\s*(?:derni[eè]res?|derniers?)\s*notifs?\b", text, re.I):
        limit = parse_export_limit(text)
        return ClassifiedIntent(
            name=CopilotIntent.NOTIFICATION_LIST, domain="notifications", export_limit=limit,
        )
    if _TRACK_LIST_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.TRACKING_LIST, domain="tracking")
    if _AGENT_CATALOG_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.AGENT_CATALOG, domain="generic")
    if _TOOL_CATALOG_RE.search(text):
        return ClassifiedIntent(name=CopilotIntent.TOOL_CATALOG, domain="generic")

    return ClassifiedIntent(name=CopilotIntent.UNKNOWN, is_contextual=ctx.is_contextual)
