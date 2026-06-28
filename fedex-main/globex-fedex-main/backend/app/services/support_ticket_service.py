"""Création ticket support — partagée route HTTP et agent Phase 11."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.support_ticket_message import SupportTicketMessage
from app.models.user import User
from app.services.activity_log_service import write_log
from app.services.help_center_service import generate_ticket_number
from app.services.user_notification_service import (
    notify_admins_new_support_ticket,
    notify_employees_new_support_ticket,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")

VALID_CATEGORIES = frozenset({"tracking", "documents", "ai", "security", "account", "other"})
VALID_PRIORITIES = frozenset({"low", "medium", "high"})


def sanitize_support_text(value: str) -> str:
    return _HTML_TAG_RE.sub("", value or "").strip()


def normalize_ticket_category(category: str | None) -> str:
    cat = (category or "other").strip().lower()
    if cat == "delivery":
        cat = "tracking"
    return cat if cat in VALID_CATEGORIES else "other"


def normalize_ticket_priority(priority: str | None) -> str:
    prio = (priority or "medium").strip().lower()
    return prio if prio in VALID_PRIORITIES else "medium"


def create_client_support_ticket(
    db: Session,
    *,
    user: User,
    subject: str,
    message: str,
    category: str = "other",
    priority: str = "medium",
    attachment_url: str | None = None,
    ip_address: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    clean_subject = sanitize_support_text(subject)[:200]
    clean_message = sanitize_support_text(message)[:4000]
    if len(clean_subject) < 3:
        raise ValueError("Subject required.")
    if len(clean_message) < 10:
        raise ValueError("Message required.")

    row = SupportTicket(
        user_id=user.id,
        subject=clean_subject,
        category=normalize_ticket_category(category),
        priority=normalize_ticket_priority(priority),
        message=clean_message,
        attachment_url=attachment_url,
        status=SupportTicketStatus.open,
    )
    db.add(row)
    db.flush()
    row.ticket_number = generate_ticket_number(row.id)
    db.add(
        SupportTicketMessage(
            ticket_id=row.id,
            author_role="user",
            author_user_id=user.id,
            body=clean_message,
            attachment_url=attachment_url,
        )
    )
    write_log(
        db,
        action="support.ticket_created",
        message=f"Nouveau ticket support de {user.email} : {clean_subject[:80]}",
        category="admin",
        level="INFO",
        user_id=user.id,
        ip_address=ip_address,
        metadata={"ticket_id": row.id, "ticket_number": row.ticket_number},
        commit=False,
    )
    notify_admins_new_support_ticket(db, row, user)
    notify_employees_new_support_ticket(db, row, user)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return {
        "ticket_id": row.id,
        "ticket_number": row.ticket_number,
        "status": row.status,
        "created_at": row.created_at,
    }
