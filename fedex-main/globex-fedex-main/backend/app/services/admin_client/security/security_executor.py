"""Exécuteur Security IDS admin — délègue au pipeline."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.security.security_pipeline import run_security_pipeline


def try_admin_security_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
    *,
    history_text: str | None = None,
    conversation_history: list[Any] | None = None,
) -> dict[str, Any] | None:
    return run_security_pipeline(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
        conversation_history=conversation_history,
    )
