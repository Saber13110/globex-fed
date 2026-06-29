"""Espace de travail gestion utilisateurs admin — gate Jarvis."""

from __future__ import annotations

import re
import unicodedata

from app.services.admin_client.users.users_followup import is_users_followup_message

_USERS_MGMT_RE = re.compile(
    r"\b("
    r"utilisateurs?|users?|comptes?|accounts?|"
    r"gestion\s+(des\s+)?utilisateurs?|user\s+management|"
    r"suspend(?:re|ez)?|r[eé]activ(?:er|ez)?|"
    r"supprim(?:er|ez)?|delete\s+user|"
    r"permissions?|quotas?|"
    r"logs?\s+(de\s+l['']?)?utilisateur|user\s+logs?|"
    r"fiche\s+utilisateur|user\s+detail|d[eé]tail\s+(du\s+)?(compte|user|utilisateur)|"
    r"renomm(?:er|ez)?|reset\s+password|mot\s+de\s+passe|"
    r"r[eé]initialis(?:er|ez)?\s+(le\s+)?mot\s+de\s+passe|"
    r"liste.{0,30}(utilisateurs?|users?|comptes?)|"
    r"list.{0,30}(utilisateurs?|users?|comptes?)|"
    r"montre.{0,20}(utilisateurs?|users?|comptes?)|"
    r"affiche.{0,20}(utilisateurs?|users?|comptes?)|"
    r"t[eé]l[eé]charg.{0,25}(pdf).{0,30}(utilisateurs?|users?|logs?)|"
    r"(pdf).{0,30}(liste.{0,15})?(utilisateurs?|users?|logs?)"
    r")\b",
    re.I,
)

_DASHBOARD_USERS_KPI_RE = re.compile(
    r"\b("
    r"utilisateurs?\s+(cr[eé][eé]s?|nouveaux?|par\s+r[oô]le|totaux?)|"
    r"nouveaux?\s+utilisateurs?|"
    r"users?\s+(by\s+role|created|new|breakdown)|"
    r"r[eé]partition\s+(des\s+)?(comptes|utilisateurs?|users?)"
    r")\b",
    re.I,
)

_USERS_KPI_QUESTION_RE = re.compile(
    r"\b(combien|how\s+many|nombre\s+de|count\s+of|total\s+de)\b.{0,40}\b(utilisateurs?|users?|comptes?)\b",
    re.I,
)

_SIGNAL_PATTERNS: dict[str, list[tuple[re.Pattern[str], float]]] = {
    "list": [
        (re.compile(r"\b(liste|list|montre|affiche|donne).{0,30}(utilisateurs?|users?|comptes?)\b", re.I), 3.0),
        (re.compile(r"\b(tous les|all)\s+(les\s+)?(utilisateurs?|users?|comptes?)\b", re.I), 3.0),
    ],
    "detail": [
        (re.compile(r"\b(fiche|d[eé]tail|infos?).{0,20}(utilisateur|user|compte)\b", re.I), 3.0),
    ],
    "logs": [
        (re.compile(r"\b(logs?|journaux?).{0,20}(utilisateur|user|compte)\b", re.I), 3.0),
    ],
    "permissions": [
        (re.compile(r"\b(permissions?|quotas?|droits?).{0,20}(utilisateur|user|compte)?\b", re.I), 2.5),
    ],
    "suspend": [
        (re.compile(r"\b(suspend(?:re|ez)?|bloqu(?:er|ez))\b", re.I), 3.0),
    ],
    "reactivate": [
        (re.compile(r"\b(r[eé]activ(?:er|ez)?|d[eé]bloqu(?:er|ez))\b", re.I), 3.0),
    ],
    "delete": [
        (re.compile(r"\b(supprim(?:er|ez)?|delete)\b", re.I), 2.5),
    ],
    "reset_password": [
        (re.compile(r"\b(reset|mot\s+de\s+passe|r[eé]initialis)\b", re.I), 2.5),
    ],
    "catalog": [
        (re.compile(r"\b(gestion\s+utilisateurs?|user\s+management)\b", re.I), 3.0),
        (re.compile(r"^\s*users?\s*$", re.I), 2.0),
        (re.compile(r"\b(utilisateurs?|users?|comptes?)\b", re.I), 1.5),
    ],
}

_SOFT_THRESHOLD = 2.0


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def normalize_users_text(message: str) -> str:
    return _normalize(message).lower()


def score_users_soft(message: str) -> float:
    text = normalize_users_text(message)
    if not text:
        return 0.0
    total = 0.0
    for patterns in _SIGNAL_PATTERNS.values():
        for pat, weight in patterns:
            if pat.search(text):
                total += weight
    return total


def is_dashboard_users_kpi(message: str) -> bool:
    return bool(_DASHBOARD_USERS_KPI_RE.search(_normalize(message)))


def is_users_workspace(message: str, *, history_text: str = "") -> bool:
    text = _normalize(message)
    if not text:
        return False
    if _USERS_KPI_QUESTION_RE.search(text):
        return False
    if is_users_followup_message(text, history_text=history_text):
        return True
    if _USERS_MGMT_RE.search(text):
        if is_dashboard_users_kpi(text) and not re.search(
            r"\b(suspend|supprim|logs?|fiche|d[eé]tail|permissions?|liste|list|renomm|mot\s+de\s+passe)\b",
            text,
            re.I,
        ):
            return False
        return True
    return score_users_soft(text) >= _SOFT_THRESHOLD
