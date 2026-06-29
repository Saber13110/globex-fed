"""Façade métier tickets support admin — lecture PostgreSQL."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.support_ticket_message import SupportTicketMessage
from app.models.user import User
from app.services.admin_client.tickets.tickets_types import TicketsToolError
from app.services.help_center_service import generate_ticket_number

_VALID_STATUSES = frozenset({
    SupportTicketStatus.open,
    SupportTicketStatus.pending,
    SupportTicketStatus.resolved,
    SupportTicketStatus.closed,
    "all",
})
_VALID_PRIORITIES = frozenset({"low", "medium", "high"})
_VALID_CATEGORIES = frozenset({"tracking", "documents", "ai", "security", "account", "other"})


def _normalize_status(status: str | None) -> str | None:
    s = (status or "").strip().lower()
    if not s or s == "all":
        return None
    if s in _VALID_STATUSES:
        return s
    return None


def _normalize_priority(priority: str | None) -> str | None:
    p = (priority or "").strip().lower()
    return p if p in _VALID_PRIORITIES else None


def _normalize_category(category: str | None) -> str | None:
    c = (category or "").strip().lower()
    return c if c in _VALID_CATEGORIES else None


def _ticket_list_dict(ticket: SupportTicket, *, user: User | None = None) -> dict[str, Any]:
    return {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "ticket_number": ticket.ticket_number or generate_ticket_number(ticket.id),
        "subject": ticket.subject,
        "message": (ticket.message or "")[:200],
        "category": ticket.category or "other",
        "priority": ticket.priority or "medium",
        "status": ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "user_name": user.full_name if user else None,
        "user_email": user.email if user else None,
    }


def _message_dict(row) -> dict[str, Any]:
    author_name = None
    if row.author and row.author_role == "admin":
        author_name = row.author.full_name or "Admin"
    elif row.author and row.author_role == "user":
        author_name = row.author.full_name
    return {
        "id": row.id,
        "author_role": row.author_role,
        "author_name": author_name,
        "body": row.body,
        "created_at": row.created_at,
    }


def list_tickets_filtered(
    db: Session,
    *,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    limit = min(max(int(limit or 20), 1), 50)
    status_filter = _normalize_status(status)
    priority_filter = _normalize_priority(priority)
    category_filter = _normalize_category(category)
    search = (q or "").strip()

    stmt = (
        select(SupportTicket, User)
        .join(User, User.id == SupportTicket.user_id)
        .order_by(SupportTicket.updated_at.desc())
    )
    if status_filter:
        stmt = stmt.where(SupportTicket.status == status_filter)
    if priority_filter:
        stmt = stmt.where(SupportTicket.priority == priority_filter)
    if category_filter:
        stmt = stmt.where(SupportTicket.category == category_filter)
    if search:
        if search.upper().startswith(("TKT", "SUP-")):
            stmt = stmt.where(SupportTicket.ticket_number.ilike(f"%{search}%"))
        else:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    SupportTicket.subject.ilike(pattern),
                    SupportTicket.message.ilike(pattern),
                    User.email.ilike(pattern),
                    User.full_name.ilike(pattern),
                )
            )

    rows = db.execute(stmt.limit(limit)).all()
    return [_ticket_list_dict(ticket, user=user) for ticket, user in rows]


def get_ticket_detail(db: Session, ticket_id: int) -> dict[str, Any]:
    ticket = db.scalar(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages).joinedload(SupportTicketMessage.author))
        .options(joinedload(SupportTicket.user))
        .where(SupportTicket.id == ticket_id)
    )
    if ticket is None:
        raise TicketsToolError("ticket_not_found")

    user = ticket.user
    data = _ticket_list_dict(ticket, user=user)
    data["message"] = ticket.message
    data["messages"] = [_message_dict(m) for m in (ticket.messages or [])]
    return data


def summarize_tickets(tickets: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for t in tickets:
        st = str(t.get("status") or "unknown")
        pr = str(t.get("priority") or "medium")
        by_status[st] = by_status.get(st, 0) + 1
        by_priority[pr] = by_priority.get(pr, 0) + 1
    return {
        "total": len(tickets),
        "by_status": by_status,
        "by_priority": by_priority,
        "tickets": tickets,
    }


def reply_to_ticket(
    db: Session,
    ticket_id: int,
    admin_id: int,
    body: str,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    """Publie une réponse admin sur un ticket (logique route HTTP / agent mission)."""
    from app.services.activity_log_service import write_log
    from app.services.admin_agent_tools import post_admin_support_reply

    ok, result = post_admin_support_reply(
        db,
        ticket_id=ticket_id,
        body=body,
        admin_id=admin_id,
    )
    if not ok:
        err = str(result.get("error") or "reply_failed")
        raise TicketsToolError(err)
    write_log(
        db,
        action="admin_tickets.reply",
        message=f"Réponse ticket #{ticket_id} via agent tickets",
        category="admin",
        level="INFO",
        actor_user_id=admin_id,
        ip_address=ip_address,
        metadata={"ticket_id": ticket_id, "source": "admin_tickets_agent"},
        commit=False,
    )
    db.commit()
    return result


def set_ticket_status(
    db: Session,
    ticket_id: int,
    admin_id: int,
    status: str,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    """Met à jour le statut d'un ticket support."""
    from app.services.activity_log_service import write_log

    status_norm = _normalize_status(status) or (status or "").strip().lower()
    if status_norm not in {
        SupportTicketStatus.open,
        SupportTicketStatus.pending,
        SupportTicketStatus.resolved,
        SupportTicketStatus.closed,
    }:
        raise TicketsToolError("invalid_status")

    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise TicketsToolError("ticket_not_found")

    previous = ticket.status
    ticket.status = status_norm
    write_log(
        db,
        action="admin_tickets.status",
        message=f"Statut ticket #{ticket_id} : {previous} → {status_norm}",
        category="admin",
        level="INFO",
        user_id=ticket.user_id,
        actor_user_id=admin_id,
        ip_address=ip_address,
        metadata={
            "ticket_id": ticket_id,
            "previous_status": previous,
            "new_status": status_norm,
            "source": "admin_tickets_agent",
        },
        commit=False,
    )
    db.commit()
    db.refresh(ticket)
    return {
        "ticket_id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status,
        "previous_status": previous,
    }
