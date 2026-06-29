from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.dashboard.dashboard_pipeline import run_dashboard_pipeline

__all__ = ["try_admin_dashboard_turn"]


def try_admin_dashboard_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
    *,
    history_text: str | None = None,
) -> dict[str, Any] | None:
    """Tour dashboard admin. None si hors périmètre."""
    return run_dashboard_pipeline(
        db,
        admin,
        session,
        message,
        user_msg_id,
        ui_language,
        history_text=history_text,
    )
