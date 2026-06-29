"""Planification déterministe des outils sécurité — sans attendre Ollama."""

from __future__ import annotations

import re
from typing import Any

_WANTS_LAST_RE = re.compile(
    r"\b(?:derni[eè]r(?:e|es)?|last|most\s+recent|plus\s+r[eé]cente?)\b",
    re.I,
)
_ATTACK_CTX_RE = re.compile(
    r"\b(?:attaque|attack|tentative|intrusion|incident|hack(?:ing)?)\b",
    re.I,
)
_ALERTS_RE = re.compile(
    r"\b(?:alertes?\s+s[eé]curit[eé]|security\s+alerts?)\b",
    re.I,
)
_SUSPICIOUS_RE = re.compile(
    r"\b(?:logs?\s+suspects?|suspicious\s+logs?|activit[eé]\s+anormal|"
    r"injection|anomal(?:ie|ies)?|actions?\s+suspectes?)\b",
    re.I,
)
_SCAN_RE = re.compile(
    r"\b(?:scan\s+s[eé]curit[eé]|audit\s+s[eé]curit[eé]|run\s+security\s+scan)\b",
    re.I,
)
_SECURITY_CTX_RE = re.compile(
    r"\b(?:s[eé]curit[eé]|security|ids|threat)\b",
    re.I,
)


def is_security_read_request(message: str) -> bool:
    return plan_security_action_tools(message) is not None


def plan_security_action_tools(message: str) -> list[tuple[str, dict[str, Any]]] | None:
    """Route analyze_security / alertes / logs suspects sans attendre Ollama."""
    text = message or ""

    if _SCAN_RE.search(text):
        return [("run_security_scan", {})]

    if _ALERTS_RE.search(text):
        return [("get_security_alerts", {})]

    if _SUSPICIOUS_RE.search(text):
        hours = 24
        m = re.search(r"(\d{1,3})\s*(?:h|heures?|hours?)", text, re.I)
        if m:
            hours = min(max(int(m.group(1)), 1), 168)
        return [("analyze_suspicious_logs", {"hours": hours, "limit": 15})]

    if _ATTACK_CTX_RE.search(text) or (
        _SECURITY_CTX_RE.search(text) and _WANTS_LAST_RE.search(text)
    ):
        limit = 1 if _WANTS_LAST_RE.search(text) else 10
        return [("analyze_security", {"limit": limit})]

    if _SECURITY_CTX_RE.search(text) and re.search(
        r"\b(?:incident|menace|threat|breach|compromis)\b",
        text,
        re.I,
    ):
        return [("analyze_security", {"limit": 10})]

    return None
