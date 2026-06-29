"""Brouillon LLM grounded pour réponses ticket support."""

from __future__ import annotations

from typing import Any

from app.services.admin_agent_brain import draft_support_reply


def draft_ticket_reply(
    message: str,
    ticket: dict[str, Any],
    *,
    lang: str = "fr",
) -> str:
    """Rédige un brouillon de réponse admin à partir du fil ticket."""
    ctx = {
        "id": ticket.get("id"),
        "ticket_number": ticket.get("ticket_number"),
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "priority": ticket.get("priority"),
        "message": ticket.get("message"),
        "user_email": ticket.get("user_email"),
        "messages": [
            {
                "author_role": m.get("author_role"),
                "body": (m.get("body") or "")[:500],
            }
            for m in (ticket.get("messages") or [])[-8:]
        ],
    }
    return draft_support_reply(message, ctx, ui_language=lang).strip()
