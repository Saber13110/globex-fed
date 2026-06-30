"""Espace de travail missions agent — gate Jarvis."""

from __future__ import annotations

import re

from app.services.admin_client.missions.missions_followup import is_missions_followup_message

_MISSIONS_MGMT_RE = re.compile(
    r"\b("
    r"missions?\s+agents?|agents?\s+missions?|"
    r"missions?\s+agent|agent\s+missions?|"
    r"missions?\s+(en\s+cours|running|echou\w*|"
    r"[eé]chou\w*|failed|fail(?:ed|ure)?|termin[eé]\w*|completed|"
    r"annul[eé]\w*|cancelled|brouillon|draft)|"
    r"mission.{0,18}echou\w*|missions?.{0,18}echou\w*|"
    r"lister\s+(les\s+)?missions?|liste\s+moi\s+(les\s+)?missions?|"
    r"liste\s+(des\s+)?missions?|liste.{0,35}missions?|"
    r"r[eé]sultats?\s+(de\s+la\s+)?mission|"
    r"logs?\s+(de\s+la\s+)?mission|journal\s+(d['']?)?ex[eé]cution|"
    r"relancer\s+(la\s+)?mission|r[eé]essayer\s+(la\s+)?mission|"
    r"annuler\s+(la\s+)?mission|supprimer\s+(la\s+)?mission|"
    r"mission\s*#\s*\d{1,8}|"
    r"#\s*\d{1,8}\s*.{0,20}mission"
    r")\b",
    re.I,
)

_PLATFORM_LOGS_ONLY_RE = re.compile(
    r"\b(journal\s+d['']?activit[eé]|activity\s+log|logs?\s+plateforme|"
    r"anomalie.{0,20}logs?)\b",
    re.I,
)


def is_missions_workspace(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _MISSIONS_MGMT_RE.search(text):
        return True
    if is_missions_followup_message(text, history_text=history_text):
        return True
    hist = history_text or ""
    if re.search(r"\bmissions?\s+agent\b", hist, re.I) and re.search(
        r"\b(r[eé]sultats?|logs?|relancer|annuler|supprimer|#)\b", text, re.I
    ):
        return True
    return False


def should_exclude_platform_logs(message: str) -> bool:
    """Évite de router « journal d'activité » vers Mission Control."""
    text = message or ""
    if _PLATFORM_LOGS_ONLY_RE.search(text) and not re.search(r"\bmission\b", text, re.I):
        return True
    return False
