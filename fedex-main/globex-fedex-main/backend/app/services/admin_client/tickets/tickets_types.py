"""Types partagés agent Tickets admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TicketsTaskType(str, Enum):
    ticket_list = "ticket_list"
    ticket_detail = "ticket_detail"
    ticket_details_batch = "ticket_details_batch"
    ticket_summary = "ticket_summary"
    ticket_reply = "ticket_reply"
    ticket_resolve = "ticket_resolve"
    ambiguous = "ambiguous"


class TicketsProfile(str, Enum):
    LIST = "list"
    DETAIL = "detail"
    DETAILS_BATCH = "details_batch"
    SUMMARY = "summary"
    CLARIFY = "clarify"
    CONFIRM = "confirm"
    DONE = "done"
    ERROR = "error"


class TicketsToolError(Exception):
    """Échec outil tickets admin."""


@dataclass
class PendingTicketAction:
    action: str
    ticket_id: int
    payload: dict[str, str] = field(default_factory=dict)


@dataclass
class TicketsPlan:
    task_type: TicketsTaskType
    ticket_id: int | None = None
    status_filter: str | None = None
    priority_filter: str | None = None
    category_filter: str | None = None
    search_query: str | None = None
    limit: int = 20
    want_pdf: bool = False
    want_draft: bool = False
    reply_body: str = ""
    target_status: str = "resolved"
    notify_email: bool = False
    profile: TicketsProfile = TicketsProfile.LIST
    raw_matches: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_candidates: list[dict[str, str]] = field(default_factory=list)
