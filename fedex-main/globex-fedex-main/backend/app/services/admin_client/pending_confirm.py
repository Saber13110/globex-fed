"""Résolution centralisée des confirmations oui/non — évite les collisions inter-agents."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.pending_resolver import resolve_latest_pending_kind


def try_admin_pending_confirm_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    ui_language: str | None,
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
    ip_address: str = "",
) -> dict[str, Any] | None:
    """
    Traite oui/non en fonction du marqueur pending le plus récent en session.
    """
    text = (message or "").strip()
    if not text:
        return None

    from app.services.admin_client.email.email_pending import (
        is_email_cancel_message,
        is_email_confirm_message,
    )
    from app.services.admin_client.reports.reports_share_pending import (
        is_share_cancel_message,
        is_share_confirm_message,
    )
    from app.services.admin_client.email.email_action_offer import (
        is_action_email_offer_accept,
        is_action_email_offer_decline,
    )
    from app.services.admin_client.users.users_pending import (
        is_users_cancel_message,
        is_users_confirm_message,
    )
    from app.services.admin_client.tickets.tickets_pending import (
        is_tickets_cancel_message,
        is_tickets_confirm_message,
    )
    from app.services.admin_client.missions.missions_pending import (
        is_missions_cancel_message,
        is_missions_confirm_message,
    )

    session_id = getattr(session, "id", None)
    latest = resolve_latest_pending_kind(
        db=db,
        chat_session_id=session_id,
        conversation_history=conversation_history,
    )
    if not latest:
        return None

    is_confirm = (
        is_email_confirm_message(text)
        or is_share_confirm_message(text)
        or is_action_email_offer_accept(text)
        or is_users_confirm_message(text)
        or is_tickets_confirm_message(text)
        or is_missions_confirm_message(text)
    )
    is_cancel = (
        is_email_cancel_message(text)
        or is_share_cancel_message(text)
        or is_action_email_offer_decline(text)
        or is_users_cancel_message(text)
        or is_tickets_cancel_message(text)
        or is_missions_cancel_message(text)
    )
    if not is_confirm and not is_cancel:
        return None

    if latest == "email_send" and (is_email_confirm_message(text) or is_email_cancel_message(text)):
        from app.services.admin_client.email.email_pipeline import run_email_pipeline

        return run_email_pipeline(
            db,
            admin,
            session,
            message,
            0,
            ui_language,
            history_text=history_text or "",
            conversation_history=conversation_history,
            ip_address=ip_address,
        )

    if latest == "email_offer" and (
        is_action_email_offer_accept(text) or is_action_email_offer_decline(text)
    ):
        from app.services.admin_client.email.email_pipeline import run_email_pipeline

        return run_email_pipeline(
            db,
            admin,
            session,
            message,
            0,
            ui_language,
            history_text=history_text or "",
            conversation_history=conversation_history,
            ip_address=ip_address,
        )

    if latest == "share" and (is_share_confirm_message(text) or is_share_cancel_message(text)):
        from app.services.admin_client.reports.reports_pipeline import run_reports_pipeline

        return run_reports_pipeline(
            db,
            admin,
            session,
            message,
            0,
            ui_language,
            history_text=history_text or "",
            conversation_history=conversation_history,
        )

    if latest == "users" and (is_users_confirm_message(text) or is_users_cancel_message(text)):
        from app.services.admin_client.users.users_pipeline import run_users_pipeline

        return run_users_pipeline(
            db,
            admin,
            session,
            message,
            0,
            ui_language,
            history_text=history_text or "",
            conversation_history=conversation_history,
            ip_address=ip_address,
        )

    if latest == "tickets" and (is_tickets_confirm_message(text) or is_tickets_cancel_message(text)):
        from app.services.admin_client.tickets.tickets_pipeline import run_tickets_pipeline

        return run_tickets_pipeline(
            db,
            admin,
            session,
            message,
            0,
            ui_language,
            history_text=history_text or "",
            conversation_history=conversation_history,
            ip_address=ip_address,
        )

    if latest == "missions" and (is_missions_confirm_message(text) or is_missions_cancel_message(text)):
        from app.services.admin_client.missions.missions_pipeline import run_missions_pipeline

        return run_missions_pipeline(
            db,
            admin,
            session,
            message,
            0,
            ui_language,
            history_text=history_text or "",
            conversation_history=conversation_history,
            ip_address=ip_address,
        )

    return None
