"""Mémoire ticket cible — relances « ce ticket », contexte liste."""

from __future__ import annotations

import re

from app.services.admin_client.tickets.tickets_followup import (
    extract_ticket_number_token,
    extract_ticket_ref,
    is_tickets_history_context,
    list_ticket_ids_from_history,
)

_TABLE_ROW_RE = re.compile(
    r"\|\s*#?(\d{1,8})\s*\|[^|\n]+\|",
    re.I,
)
_PRONOUN_RE = re.compile(
    r"\b("
    r"ce\s+ticket|cet\s+ticket|cette\s+demande|"
    r"celui(?:-ci)?|celle(?:-ci)?|"
    r"le\s+m[eê]me|the\s+same\s+ticket|this\s+ticket|that\s+ticket"
    r")\b",
    re.I,
)


def is_pronoun_ticket_reference(message: str) -> bool:
    return bool(_PRONOUN_RE.search(message or ""))


def extract_focus_ticket_from_history(history_text: str) -> tuple[int | None, str | None]:
    hist = history_text or ""
    if not hist:
        return None, None

    table_matches = list(_TABLE_ROW_RE.finditer(hist))
    if table_matches:
        return int(table_matches[-1].group(1)), None

    ref = extract_ticket_ref(hist, history_text=hist)
    if ref is not None:
        return ref, None

    tkt = extract_ticket_number_token(hist)
    if tkt and is_tickets_history_context(hist):
        return None, tkt

    return None, None


def resolve_pronoun_or_context(
    message: str,
    history_text: str,
    *,
    list_row_index: int | None = None,
) -> tuple[int | None, str | None]:
    if list_row_index is not None:
        ids = list_ticket_ids_from_history(history_text)
        if 0 <= list_row_index < len(ids):
            return ids[list_row_index], None

    if is_pronoun_ticket_reference(message) or not extract_ticket_ref(message):
        uid, tkt = extract_focus_ticket_from_history(history_text)
        if uid or tkt:
            return uid, tkt

    return extract_focus_ticket_from_history(history_text)
