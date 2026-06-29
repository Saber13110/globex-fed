"""Outils agent tickets admin — délégation tickets_service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.admin_client.tickets import tickets_service
from app.services.admin_client.tickets.tickets_types import TicketsPlan


def list_tickets(db: Session, plan: TicketsPlan) -> list[dict[str, Any]]:
    return tickets_service.list_tickets_filtered(
        db,
        status=plan.status_filter,
        priority=plan.priority_filter,
        category=plan.category_filter,
        q=plan.search_query,
        limit=plan.limit,
    )


def get_ticket_detail(db: Session, ticket_id: int) -> dict[str, Any]:
    return tickets_service.get_ticket_detail(db, ticket_id)


def build_summary(db: Session, plan: TicketsPlan) -> dict[str, Any]:
    tickets = list_tickets(db, plan)
    return tickets_service.summarize_tickets(tickets)


def build_details_batch(db: Session, plan: TicketsPlan, *, max_items: int = 5) -> dict[str, Any]:
    tickets = list_tickets(db, plan)
    details: list[dict[str, Any]] = []
    for row in tickets[:max_items]:
        try:
            details.append(get_ticket_detail(db, int(row["id"])))
        except Exception:
            continue
    return {"tickets": tickets, "details": details}
