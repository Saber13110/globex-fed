"""Suite de dialogue Gestion utilisateurs — relances après liste."""

from __future__ import annotations

import re

_USERS_HISTORY_MARKERS = re.compile(
    r"Gestion utilisateurs Admin|Admin User Management|"
    r"Liste des utilisateurs|User list|"
    r"Action effectu[eé]e|Action completed|"
    r"Compte\s+[^\s]+@[^\s]+\s+suspendu|"
    r"Utilisateurs\s*\(|Users\s*\(|"
    r"\#\d{1,8}\s+[^\s]+@[^\s]+|"
    r"\|\s*\d{1,8}\s*\|[^|\n]+@[^|\n]+",
    re.I,
)

_FOLLOWUP_ACTION_RE = re.compile(
    r"\b("
    r"d[eé]tail|fiche|infos?|permissions?|quotas?|logs?|journaux?|"
    r"suspend|suspendre|r[eé]?activ|reactiv|reactive|supprim|delete|"
    r"renomm|rename|mot\s+de\s+passe|password|reset|"
    r"t[eé]l[eé]charg|telecharg|download|consulte|montre|affiche"
    r")\b",
    re.I,
)

_USER_HASH_RE = re.compile(r"#\s*(\d{1,8})\b")
_USER_REF_RE = re.compile(
    r"\b(?:utilisateur|user|compte|account)\s*#?\s*(\d{1,8})\b",
    re.I,
)
_USER_LE_RE = re.compile(
    r"\b(?:le|la|num[eé]ro|n°)\s*#?\s*(\d{1,8})\b",
    re.I,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_LIST_ROW_RE = re.compile(
    r"^\s*\|\s*#?(\d{1,8})\s*\|",
    re.MULTILINE,
)
_LIST_ROW_PLAIN_RE = re.compile(
    r"^\s*\|\s*(\d{1,8})\s*\|",
    re.MULTILINE,
)


def is_users_history_context(history_text: str) -> bool:
    return bool(_USERS_HISTORY_MARKERS.search(history_text or ""))


def is_users_followup_message(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text or not is_users_history_context(history_text):
        return False
    if _EMAIL_RE.search(text):
        return True
    if extract_user_ref(text, history_text=history_text) is not None:
        return True
    return bool(_FOLLOWUP_ACTION_RE.search(text))


def extract_user_ref(message: str, *, history_text: str = "") -> int | None:
    text = (message or "").strip()
    if not text:
        return None

    m = _USER_HASH_RE.search(text)
    if m:
        return int(m.group(1))

    m = _USER_REF_RE.search(text)
    if m:
        return int(m.group(1))

    if is_users_history_context(history_text):
        m = _USER_LE_RE.search(text)
        if m:
            return int(m.group(1))

    return None


def extract_email_from_message(message: str) -> str | None:
    m = _EMAIL_RE.search(message or "")
    return m.group(0) if m else None


def list_user_ids_from_history(history_text: str) -> list[int]:
    """IDs ordonnés tels qu'affichés dans le tableau liste."""
    ids: list[int] = []
    for pattern in (_LIST_ROW_RE, _LIST_ROW_PLAIN_RE):
        for m in pattern.finditer(history_text or ""):
            uid = int(m.group(1))
            if uid not in ids:
                ids.append(uid)
    return ids
