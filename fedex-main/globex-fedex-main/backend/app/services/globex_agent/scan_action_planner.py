"""Planification déterministe des outils de scan lecture seule."""

from __future__ import annotations

import re
from typing import Any

_DORMANT_RE = re.compile(
    r"\b(?:inactifs?|dormants?|sans\s+activit[eé]|inactivit[eé])\b",
    re.I,
)
_ACCOUNT_CTX_RE = re.compile(
    r"\b(?:compte|comptes|utilisateur|utilisateurs|client|clients)\b",
    re.I,
)
_SLA_RE = re.compile(
    r"\b(?:sla|retard|d[eé]pass[eé])\b",
    re.I,
)
_TICKET_RE = re.compile(r"\b(?:ticket|tickets|support)\b", re.I)


def is_dormant_scan_request(message: str) -> bool:
    text = message or ""
    return bool(_DORMANT_RE.search(text) and _ACCOUNT_CTX_RE.search(text))


def is_sla_scan_request(message: str) -> bool:
    text = message or ""
    return bool(_SLA_RE.search(text) and _TICKET_RE.search(text))


def plan_scan_action_tools(message: str) -> list[tuple[str, dict[str, Any]]] | None:
    """Route scan_dormant_accounts / scan_ticket_sla sans attendre Ollama."""
    text = message or ""
    if is_dormant_scan_request(text):
        days = 30
        m = re.search(r"(\d{2,3})\s*(?:jours?|j\b|days?)", text, re.I)
        if m:
            days = min(max(int(m.group(1)), 7), 365)
        return [("scan_dormant_accounts", {"days": days, "limit": 15})]
    if is_sla_scan_request(text):
        return [("scan_ticket_sla", {"limit": 15})]
    return None
