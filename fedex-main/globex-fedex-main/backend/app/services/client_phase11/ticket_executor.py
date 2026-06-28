"""Exécution création ticket support — Phase 11."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.client_phase11.ticket_draft_pointer import TicketDraft, clear_ticket_draft
from app.services.support_ticket_service import (
    create_client_support_ticket,
    normalize_ticket_category,
    normalize_ticket_priority,
    sanitize_support_text,
)


def execute_open_support_ticket(
    db: Session,
    *,
    user: User,
    session_id: int,
    draft: TicketDraft,
    lang: str,
) -> dict[str, Any]:
    subject = sanitize_support_text(draft.subject)[:200]
    message = sanitize_support_text(draft.message)[:4000]
    if len(subject) < 3:
        subject = "Demande client via chat"
    if len(message) < 10:
        message = "Signalement via le chat client FedEx."

    created = create_client_support_ticket(
        db,
        user=user,
        subject=subject,
        message=message,
        category=normalize_ticket_category(draft.category),
        priority=normalize_ticket_priority(draft.priority),
        attachment_url=None,
        ip_address=None,
        commit=False,
    )
    clear_ticket_draft(session_id)
    ticket_no = created["ticket_number"]
    if lang == "en":
        reply = (
            f"**Ticket opened** — reference `{ticket_no}`.\n\n"
            "Our support team has been notified. "
            "Track progress in **Help → My tickets**."
        )
    else:
        reply = (
            f"**Ticket ouvert** — référence `{ticket_no}`.\n\n"
            "L'équipe support a été notifiée. "
            "Suivez l'avancement dans **Aide → Mes tickets**."
        )
    return {
        "reply": reply,
        "intent": "support_ticket_created",
        "ticket_number": ticket_no,
        "ticket_id": created["ticket_id"],
    }
