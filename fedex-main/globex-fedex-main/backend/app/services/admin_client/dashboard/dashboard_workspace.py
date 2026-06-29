"""Espace de travail dashboard admin — gate avant suivi/PDF/notifs."""

from __future__ import annotations

import re

_PLATFORM_RE = re.compile(
    r"\b("
    r"plateforme|platform|dashboard|tableau\s+de\s+bord|command\s+center|"
    r"kpi[s]?|statistiques?|stats|m[eé]triques?|overview|"
    r"sant[eé]\s+(du\s+)?syst[eè]me|system\s+health|"
    r"activit[eé]\s+(r[eé]cente|globale|plateforme|suspecte?)|recent\s+activity|"
    r"suspicious\s+(activity|security)|"
    r"audit|journaux?|logs\s+admin|"
    r"utilisateurs?\s+(cr[eé][eé]s?|nouveaux?|par\s+r[oô]le|totaux?)|"
    r"nouveaux?\s+utilisateurs?|"
    r"users?\s+(by\s+role|created|new|breakdown)|"
    r"r[eé]partition\s+(des\s+)?comptes|"
    r"conversations?\s+ia|ai\s+conversations?|"
    r"retards?\s+(globaux?|exp[eé]dition|colis)?|delayed\s+shipments?|"
    r"colis\s+(probl[eé]matiques?|en\s+retard)|shipments?\s+at\s+risk|"
    r"rapport\s+(des\s+)?retards?|delay\s+report|"
    r"anomal|suspect|incident\s+ouvert|"
    r"probleme|souci|panne|alerte|priorit|surveiller|important|chiffres?\s+(importants?|cles?|a\s+surveiller)|"
    r"explique|simplement|en clair|"
    r"[eé]tat\s+(de\s+la\s+)?(plateforme|globex)|"
    r"r[eé]sum[eé]\s+(de\s+la\s+)?plateforme|platform\s+summary|"
    r"aujourd[\u2019']hui|today[\u2019]s?\s+status|situation\s+globale"
    r")\b",
    re.I,
)

_REPORT_PLATFORM_RE = re.compile(
    r"\brapport\s+(des\s+)?(retards?|plateforme|kpi|activit[eé])|"
    r"(delay|platform|performance)\s+report\b",
    re.I,
)


def is_dashboard_report_message(message: str) -> bool:
    """Rapport dashboard (retards / plateforme) — pas PDF colis."""
    text = (message or "").strip()
    return bool(_REPORT_PLATFORM_RE.search(text) or re.search(
        r"\brapport\s+(des\s+)?retards?\b", text, re.I
    ))


def is_dashboard_workspace(message: str) -> bool:
    """Vrai si le tour relève du dashboard admin (KPI, retards globaux, audit…)."""
    text = (message or "").strip()
    if not text:
        return False
    if _REPORT_PLATFORM_RE.search(text):
        return True
    return bool(_PLATFORM_RE.search(text))
