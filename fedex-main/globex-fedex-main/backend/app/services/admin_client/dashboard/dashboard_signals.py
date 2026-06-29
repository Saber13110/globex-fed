"""Signaux dashboard — scoring multi-dimension pour reformulations."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_SIGNAL_PATTERNS: dict[str, list[tuple[re.Pattern[str], float]]] = {
    "overview": [
        (re.compile(r"\b(plateforme|platform|dashboard|tableau de bord|command center)\b", re.I), 2.5),
        (re.compile(r"\b(kpi|statistiques?|stats|metriques?|overview)\b", re.I), 2.0),
        (re.compile(r"\b(etat|situation|vue d.ensemble|bilan|global)\b", re.I), 2.0),
        (re.compile(r"\b(resume|summary|synthese)\b", re.I), 1.0),
    ],
    "activity": [
        (re.compile(r"\b(activite recente|recent activity|timeline)\b", re.I), 2.5),
        (re.compile(r"\b(derniers? evenements?|what happened|mouvements?)\b", re.I), 2.5),
        (re.compile(r"\b(s.est passe|fil d.activite|historique recent)\b", re.I), 2.0),
        (re.compile(r"\bactivite\b", re.I), 1.5),
    ],
    "health": [
        (re.compile(r"\b(probleme|souci|panne|down|alerte|anomal)\b", re.I), 2.5),
        (re.compile(r"\b(plateforme va bien|ca va|normal|incident)\b", re.I), 2.0),
        (re.compile(r"\b(sante|health|operational)\b", re.I), 2.0),
    ],
    "delays": [
        (re.compile(r"\b(retards?|delayed|problematiques?|at risk)\b", re.I), 2.5),
        (re.compile(r"\bcolis en (retard|souffrance)\b", re.I), 2.5),
    ],
    "delay_report": [
        (re.compile(r"\brapport (des )?retards?\b", re.I), 3.0),
        (re.compile(r"\bdelay report\b", re.I), 3.0),
    ],
    "audit": [
        (re.compile(r"\b(audit|journaux?|logs admin|suspect|intrusion|ids)\b", re.I), 2.5),
        (re.compile(r"\bactivite suspecte\b", re.I), 2.5),
    ],
    "conversations": [
        (re.compile(r"\b(conversations? ia|ai conversations?|chats assistant)\b", re.I), 2.5),
    ],
    "users": [
        (re.compile(r"\b(utilisateurs? par role|users by role|repartition des comptes)\b", re.I), 2.5),
        (re.compile(r"\b(breakdown users?|roles et statuts)\b", re.I), 2.0),
    ],
    "new_users": [
        (re.compile(r"\b(nouveaux? utilisateurs?|new users?|inscriptions recentes)\b", re.I), 2.5),
        (re.compile(r"\busers? created\b", re.I), 2.0),
    ],
    "kpi_advisory": [
        (re.compile(r"\b(priorit[eé]?|important|surveiller|regarder en premier)\b", re.I), 2.5),
        (re.compile(r"\b(chiffres? cles?|indicateurs?|metriques? principales?)\b", re.I), 2.0),
        (re.compile(r"\bchiffres?\b", re.I), 1.5),
    ],
    "explain": [
        (re.compile(r"\b(explique|simplement|en clair|decortique|schema)\b", re.I), 2.0),
    ],
}

_WIN_THRESHOLD = 2.0
_GREY_ZONE = 1.0


def normalize_message_text(message: str) -> str:
    raw = (message or "").strip().lower()
    folded = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def score_dashboard_signals(message: str) -> dict[str, float]:
    text = normalize_message_text(message)
    scores: dict[str, float] = {k: 0.0 for k in _SIGNAL_PATTERNS}

    for dim, patterns in _SIGNAL_PATTERNS.items():
        for pat, weight in patterns:
            if pat.search(text):
                scores[dim] += weight

    if re.search(r"\b(resume|recap|synthese|summary)\b", text):
        if scores["activity"] > 0:
            scores["activity"] += 2.0
        elif scores["overview"] > 0:
            scores["overview"] += 2.0

    if re.search(r"\b(probleme|souci|panne)\b", text):
        scores["health"] += 1.5

    return scores


def pick_top_signal(scores: dict[str, float]) -> tuple[str | None, float, float]:
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if not ranked or ranked[0][1] < _WIN_THRESHOLD:
        return None, 0.0, 0.0
    top_name, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    return top_name, top_score, second_score


def is_grey_zone(scores: dict[str, float]) -> bool:
    top, top_score, second = pick_top_signal(scores)
    if top is None:
        return max(scores.values(), default=0) >= _GREY_ZONE
    return top_score - second < _GREY_ZONE and top_score < _WIN_THRESHOLD + 1.0


def signal_to_task_type(signal: str) -> str:
    mapping = {
        "overview": "platform_overview",
        "activity": "recent_activity",
        "health": "platform_overview",
        "delays": "delayed_shipments",
        "delay_report": "quick_delay_report",
        "audit": "recent_audit",
        "conversations": "recent_ai_conversations",
        "users": "users_breakdown",
        "new_users": "new_users_period",
        "kpi_advisory": "platform_overview",
        "explain": "platform_overview",
    }
    return mapping.get(signal, "platform_overview")
