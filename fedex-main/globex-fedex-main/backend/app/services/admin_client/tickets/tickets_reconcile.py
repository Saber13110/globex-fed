"""Reconcile plan tickets — paramètres message sans search_query parasite."""

from __future__ import annotations

import re

from app.services.admin_client.tickets.tickets_followup import (
    extract_email_from_message,
    extract_ticket_number_token,
    extract_ticket_ref,
)
from app.services.admin_client.tickets.tickets_intent import (
    _extract_category_filter,
    _extract_priority_filter,
    _extract_status_filter,
)
from app.services.admin_client.tickets.tickets_types import TicketsPlan, TicketsProfile, TicketsTaskType
from app.services.admin_client.tickets.tickets_workspace import normalize_tickets_text

_SEARCH_STOP = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "de",
        "du",
        "et",
        "ou",
        "ticket",
        "tickets",
        "support",
        "liste",
        "list",
        "montre",
        "affiche",
        "donne",
        "moi",
        "tous",
        "all",
        "ouvert",
        "ouverts",
        "open",
        "pending",
        "resolu",
        "resolved",
        "ferme",
        "closed",
        "resume",
        "résumé",
        "summary",
        "je",
        "veux",
        "user",
        "users",
        "utilisateur",
        "utilisateurs",
        "pour",
    }
)

_PROFILE_FOR_TASK = {
    TicketsTaskType.ticket_list: TicketsProfile.LIST,
    TicketsTaskType.ticket_detail: TicketsProfile.DETAIL,
    TicketsTaskType.ticket_details_batch: TicketsProfile.DETAILS_BATCH,
    TicketsTaskType.ticket_summary: TicketsProfile.SUMMARY,
}


def _extract_search_query(text: str) -> str | None:
    norm = normalize_tickets_text(text)
    tokens = [t for t in re.findall(r"[a-z0-9_-]+", norm) if t not in _SEARCH_STOP and len(t) > 2]
    if not tokens:
        return None
    if tokens[0].startswith("tkt"):
        return tokens[0].upper()
    if len(tokens) >= 2:
        return " ".join(tokens[:3])
    return tokens[0]


def reconcile_tickets_plan(message: str, plan: TicketsPlan, *, history_text: str = "") -> TicketsPlan:
    text = normalize_tickets_text(message)

    tid = plan.ticket_id or extract_ticket_ref(message, history_text=history_text)
    if tid:
        plan.ticket_id = tid

    email = extract_email_from_message(message)
    if email:
        plan.search_query = email

    tkt = extract_ticket_number_token(message)
    if tkt and not plan.ticket_id:
        plan.search_query = tkt

    if not plan.status_filter:
        plan.status_filter = _extract_status_filter(text)
    if not plan.priority_filter:
        plan.priority_filter = _extract_priority_filter(text)
    if not plan.category_filter:
        plan.category_filter = _extract_category_filter(text)

    if plan.task_type in {
        TicketsTaskType.ticket_list,
        TicketsTaskType.ticket_summary,
        TicketsTaskType.ticket_details_batch,
    }:
        if not plan.search_query and not (
            plan.status_filter or plan.priority_filter or plan.category_filter
        ):
            plan.search_query = _extract_search_query(text)
    elif plan.task_type == TicketsTaskType.ticket_detail:
        if not plan.ticket_id and not plan.search_query:
            q = _extract_search_query(text)
            if q and not q.upper().startswith("TKT"):
                plan.search_query = q

    if plan.task_type in _PROFILE_FOR_TASK:
        plan.profile = _PROFILE_FOR_TASK[plan.task_type]

    return plan
