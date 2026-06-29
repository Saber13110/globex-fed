"""Mémoire utilisateur cible — relances « cet utilisateur », contexte logs/fiche."""

from __future__ import annotations

import re

from app.services.admin_client.users.users_followup import (
    extract_email_from_message,
    extract_user_ref,
    is_users_history_context,
    list_user_ids_from_history,
)

_LOGS_HEADER_RE = re.compile(
    r"Logs\s*—\s*#?(\d{1,8})\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    re.I,
)
_FICHE_HEADER_RE = re.compile(
    r"#(\d{1,8})\s*—\s*[^\n]+",
)
_CONFIRM_USER_RE = re.compile(
    r"#(\d{1,8})\s+[^\n]+\n-\s*(\S+@\S+)",
    re.I,
)
_DONE_ACCOUNT_RE = re.compile(
    r"Compte\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\s+"
    r"(?:suspendu|r[eé]activ[eé]|supprim[eé]|renomm[eé])",
    re.I,
)
_TABLE_ROW_RE = re.compile(
    r"\|\s*(\d{1,8})\s*\|[^|\n]+\|([^|\n]+@[^|\n]+)\|",
    re.I,
)
_PRONOUN_RE = re.compile(
    r"\b("
    r"cet(?:te)?|ce\s+compte|ce|celui(?:-ci)?|celle(?:-ci)?|"
    r"le\s+m[eê]me|la\s+m[eê]me|the\s+same|this\s+user|that\s+user"
    r")\b",
    re.I,
)


def is_pronoun_user_reference(message: str) -> bool:
    return bool(_PRONOUN_RE.search(message or ""))


def extract_focus_user_from_history(history_text: str) -> tuple[int | None, str | None]:
    """Dernier utilisateur cité dans le fil (priorité aux messages récents)."""
    hist = history_text or ""
    if not hist:
        return None, None

    done_matches = list(_DONE_ACCOUNT_RE.finditer(hist))
    if done_matches:
        return None, done_matches[-1].group(1).strip()

    log_matches = list(_LOGS_HEADER_RE.finditer(hist))
    if log_matches:
        m = log_matches[-1]
        return int(m.group(1)), m.group(2)

    confirm_matches = list(_CONFIRM_USER_RE.finditer(hist))
    if confirm_matches:
        m = confirm_matches[-1]
        return int(m.group(1)), m.group(2)

    table_matches = list(_TABLE_ROW_RE.finditer(hist))
    if table_matches:
        m = table_matches[-1]
        return int(m.group(1)), m.group(2).strip()

    ref = extract_user_ref(hist, history_text=hist)
    if ref is not None:
        email = extract_email_from_message(hist)
        return ref, email

    emails = re.findall(
        r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
        hist,
    )
    if emails and is_users_history_context(hist):
        return None, emails[-1]

    fiche_matches = list(_FICHE_HEADER_RE.finditer(hist))
    if fiche_matches and is_users_history_context(hist):
        return int(fiche_matches[-1].group(1)), None

    return None, None


def resolve_pronoun_or_context(
    message: str,
    history_text: str,
    *,
    list_row_index: int | None = None,
) -> tuple[int | None, str | None]:
    if list_row_index is not None:
        ids = list_user_ids_from_history(history_text)
        if 0 <= list_row_index < len(ids):
            return ids[list_row_index], None

    if is_pronoun_user_reference(message) or not extract_email_from_message(message):
        uid, email = extract_focus_user_from_history(history_text)
        if uid or email:
            return uid, email

    return extract_focus_user_from_history(history_text)
