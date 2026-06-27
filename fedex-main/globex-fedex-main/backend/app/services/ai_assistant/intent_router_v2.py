"""Classification d'intention avancée — COUNT, LIST, EXPORT, ANALYZE, etc."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.services.ai_assistant.entity_memory import EntityMemory, is_contextual_reference, is_follow_up_message, _PRONOUN_TRACKING_RE

ActionType = Literal[
    "COUNT",
    "LIST",
    "SEARCH",
    "ANALYZE",
    "EXPORT",
    "COMPARE",
    "SUMMARIZE",
    "TRACK",
    "REPORT",
    "SECURITY",
]

Domain = Literal[
    "users",
    "notifications",
    "tracking",
    "logs",
    "tickets",
    "conversations",
    "security",
    "reports",
    "generic",
]

_COUNT_RE = re.compile(
    r"\b(combien|nombre|how many|count|total|quantit[eé])\b",
    re.I,
)
_LIST_RE = re.compile(
    r"\b(liste|lister|donne[- ]moi|donne moi|montre|affiche|voir|quels?|quelles?|show|list)\b",
    re.I,
)
_ANALYZE_RE = re.compile(
    r"\b(analyse|analyser|analyze|examine|diagnostic)\b",
    re.I,
)
_EXPORT_RE = re.compile(
    r"\b(export|exporte|g[eé]n[eè]re|fournis|t[eé]l[eé]charge|pdf|xlsx|excel|word|docx)\b",
    re.I,
)
_COMPARE_RE = re.compile(r"\b(compare|comparer|comparison|vs\.?|versus)\b", re.I)
_SUMMARIZE_RE = re.compile(
    r"\b(r[eé]sume|resume|synth[eè]se|synthese|summarize|summary|r[eé]cap)\b",
    re.I,
)
_TRACK_RE = re.compile(
    r"\b(suis|suivre|track|tracking|colis|exp[eé]dition|livraison|o[uù]\s+est)\b",
    re.I,
)
_REPORT_RE = re.compile(r"\b(rapport|report|bilan|kpi|dashboard)\b", re.I)
_SECURITY_RE = re.compile(
    r"\b(s[eé]curit[eé]|suspicious|menace|incident|intrusion|ids)\b",
    re.I,
)
_SEARCH_RE = re.compile(r"\b(cherche|recherche|search|trouve|find)\b", re.I)

_DOMAIN_PATTERNS: list[tuple[Domain, re.Pattern[str]]] = [
    ("notifications", re.compile(r"\b(notifs?|notifications?|alertes?)\b", re.I)),
    ("logs", re.compile(r"\b(logs?|journaux|activit[eé])\b", re.I)),
    ("tracking", re.compile(r"\b(tracking|colis|exp[eé]ditions?|shipments?|suivi)\b", re.I)),
    ("users", re.compile(r"\b(users?|utilisateurs?|comptes?|admins?)\b", re.I)),
    ("tickets", re.compile(r"\b(tickets?|support|plaintes?)\b", re.I)),
    ("conversations", re.compile(r"\b(conversations?|discussions?|chats?)\b", re.I)),
    ("security", re.compile(r"\b(s[eé]curit[eé]|suspicious|incidents?)\b", re.I)),
    ("reports", re.compile(r"\b(rapports?|bilan|synth[eè]se plateforme)\b", re.I)),
]

_LIMIT_RE = re.compile(
    r"\b(\d+)\s*(?:derni[eè]res?|derniers?|last|recentes?|r[eé]centes?)?\b",
    re.I,
)
_PDF_RE = re.compile(r"\bpdf\b", re.I)
_XLSX_RE = re.compile(r"\b(xlsx|excel)\b", re.I)
_WORD_RE = re.compile(r"\b(word|docx)\b", re.I)
_ACTIVE_RE = re.compile(r"\b(actifs?|active)\b", re.I)
_SUSPENDED_RE = re.compile(r"\b(suspendu[s]?|suspended)\b", re.I)


@dataclass
class IntentV2:
    action: ActionType
    domain: Domain
    specific_intent: str
    limit: int | None = None
    export_format: str | None = None
    is_contextual_reference: bool = False
    filters: dict[str, str] | None = None


def _detect_domain(text: str, memory: EntityMemory | None) -> Domain:
    if _REPORT_RE.search(text):
        return "reports"

    found: list[Domain] = []
    for name, pattern in _DOMAIN_PATTERNS:
        if pattern.search(text):
            found.append(name)
    if len(found) == 1:
        return found[0]

    if memory and memory.last_tracking_number and (
        _PRONOUN_TRACKING_RE.search(text) or is_follow_up_message(text)
    ) and not _REPORT_RE.search(text):
        return "tracking"
    if memory and memory.last_module and is_contextual_reference(text):
        mod = memory.last_module
        if mod in {"users", "notifications", "tracking", "logs", "tickets", "conversations", "security", "reports"}:
            return mod  # type: ignore[return-value]
    if "notifications" in found:
        return "notifications"
    if memory and memory.last_module == "notifications" and is_contextual_reference(text):
        return "notifications"
    return found[0] if found else "generic"


def _detect_action(text: str, *, domain: Domain, memory: EntityMemory | None) -> ActionType:
    contextual = is_contextual_reference(text)
    tracking_follow_up = bool(
        memory
        and memory.last_tracking_number
        and (_PRONOUN_TRACKING_RE.search(text) or is_follow_up_message(text))
    )

    if _EXPORT_RE.search(text) or (_PDF_RE.search(text) or _XLSX_RE.search(text) or _WORD_RE.search(text)):
        if contextual or (memory and memory.has_exportable_context()):
            return "EXPORT"
        if _EXPORT_RE.search(text) or _PDF_RE.search(text) or _XLSX_RE.search(text):
            return "EXPORT"

    if _COUNT_RE.search(text):
        return "COUNT"
    if _SUMMARIZE_RE.search(text):
        return "SUMMARIZE"
    if _COMPARE_RE.search(text):
        return "COMPARE"
    if _ANALYZE_RE.search(text):
        return "ANALYZE"
    if _TRACK_RE.search(text) or tracking_follow_up:
        return "TRACK"
    if _REPORT_RE.search(text):
        return "REPORT"
    if _SECURITY_RE.search(text):
        return "SECURITY"
    if _SEARCH_RE.search(text):
        return "SEARCH"
    if _LIST_RE.search(text):
        return "LIST"
    if contextual and memory:
        if memory.last_export_dataset or memory.last_notifications:
            return "EXPORT"
    return "LIST"


def _parse_limit(text: str) -> int | None:
    m = _LIMIT_RE.search(text)
    if m:
        return min(max(int(m.group(1)), 1), 50)
    m = re.search(r"\b(dernier|derniers|dernières|dernieres)\s+(\d{1,2})\b", text, re.I)
    if m:
        return min(max(int(m.group(2)), 1), 50)
    return None


def _parse_export_format(text: str) -> str | None:
    if _PDF_RE.search(text):
        return "pdf"
    if _XLSX_RE.search(text):
        return "xlsx"
    if _WORD_RE.search(text):
        return "docx"
    if _EXPORT_RE.search(text):
        return "pdf"
    return None


def _build_specific_intent(action: ActionType, domain: Domain, text: str) -> str:
    parts = [action.lower()]
    if domain != "generic":
        parts.append(domain)
    if _ACTIVE_RE.search(text):
        parts.insert(1, "active")
    elif _SUSPENDED_RE.search(text):
        parts.insert(1, "suspended")
    if action == "EXPORT" and is_contextual_reference(text):
        parts.insert(0, "context")
    return "_".join(parts)


def classify_intent_v2(
    message: str,
    *,
    memory: EntityMemory | None = None,
) -> IntentV2:
    """Classifie une question admin en action + domaine + intent spécifique."""
    text = (message or "").strip()
    domain = _detect_domain(text, memory)
    action = _detect_action(text, domain=domain, memory=memory)
    contextual = is_contextual_reference(text)

    if contextual and not domain and memory and memory.last_module:
        domain_map = {
            "users": "users",
            "notifications": "notifications",
            "tracking": "tracking",
            "logs": "logs",
            "tickets": "tickets",
            "security": "security",
            "reports": "reports",
        }
        domain = domain_map.get(memory.last_module, "generic")  # type: ignore[assignment]

    if action == "EXPORT" and contextual:
        action = "EXPORT"

    filters: dict[str, str] = {}
    if _ACTIVE_RE.search(text):
        filters["status"] = "active"
    if _SUSPENDED_RE.search(text):
        filters["status"] = "suspended"

    specific = _build_specific_intent(action, domain, text)
    if action == "COUNT" and domain == "users" and filters.get("status") == "active":
        specific = "count_active_users"
    elif action == "LIST" and domain == "users" and filters.get("status") == "active":
        specific = "list_active_users"
    elif action == "EXPORT" and contextual:
        fmt = _parse_export_format(text) or "pdf"
        specific = f"export_context_{fmt}"

    return IntentV2(
        action=action,
        domain=domain,
        specific_intent=specific,
        limit=_parse_limit(text) or (memory.last_limit if memory else None),
        export_format=_parse_export_format(text),
        is_contextual_reference=contextual,
        filters=filters or None,
    )
