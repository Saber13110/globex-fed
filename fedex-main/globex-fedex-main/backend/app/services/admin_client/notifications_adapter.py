"""Adaptateur notifications admin — Phase 5 sur PlatformNotification (cloche).

Réutilise routeur + exécuteur Phase 5 en patchant fetch/mark/summary pour la
plateforme admin. Normalise le plan (liste par défaut, limite « deux », etc.)
et garantit une réponse pour tout message workspace (pas de retour kernel).
"""

from __future__ import annotations

import contextlib
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.admin_notification_plan import (
    reconcile_admin_notification_plan,
)
from app.services.admin_client.admin_notification_summary import (
    generate_admin_platform_notifications_summary,
)
from app.services.admin_client.platform_notification_fetch import (
    fetch_platform_notifications_for_query,
    mark_all_platform_notifications_read,
)
from app.services.client_phase5.notification_filters import (
    detect_read_intent,
    fallback_plan_from_message,
    is_notification_workspace,
)
from app.services.client_phase5 import notification_executor as client_notification_executor
from app.services.client_phase5 import notification_service as client_notification_service
from app.services.client_phase5.router import (
    _execute_plan,
    _read_clarification_followup_plan,
    plan_notifications_task,
)


def is_mark_read_intent(message: str) -> bool:
    """Utilisé par pipeline._should_engage pour les formulations « marquer … notif »."""
    return detect_read_intent(message or "") == "mark_all"


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def _tag_admin_turn(turn: dict[str, Any] | None) -> dict[str, Any] | None:
    if turn is None:
        return None
    turn["source"] = turn.get("source") or "admin_notifications"
    return turn


@contextlib.contextmanager
def _platform_notification_backend():
    prev_fetch_svc = client_notification_service.fetch_notifications_for_query
    prev_fetch_exec = client_notification_executor.fetch_notifications_for_query
    prev_mark = client_notification_executor.mark_all_user_notifications_read
    prev_summary = client_notification_executor.generate_notifications_summary
    client_notification_service.fetch_notifications_for_query = (
        fetch_platform_notifications_for_query
    )
    client_notification_executor.fetch_notifications_for_query = (
        fetch_platform_notifications_for_query
    )
    client_notification_executor.mark_all_user_notifications_read = (
        mark_all_platform_notifications_read
    )
    client_notification_executor.generate_notifications_summary = (
        generate_admin_platform_notifications_summary
    )
    try:
        yield
    finally:
        client_notification_service.fetch_notifications_for_query = prev_fetch_svc
        client_notification_executor.fetch_notifications_for_query = prev_fetch_exec
        client_notification_executor.mark_all_user_notifications_read = prev_mark
        client_notification_executor.generate_notifications_summary = prev_summary


def _resolve_plan(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    lang = _lang(ui_language, admin)

    followup = _read_clarification_followup_plan(
        db, session.id, message, lang=lang
    )
    if followup is not None:
        return reconcile_admin_notification_plan(message, followup)

    if not is_notification_workspace(message):
        return None

    plan = plan_notifications_task(
        db,
        admin,
        session,
        message,
        exclude_message_id=user_msg_id,
        ui_language=ui_language,
    )
    if plan is not None:
        return reconcile_admin_notification_plan(message, plan)

    fallback = fallback_plan_from_message(message, lang=lang)
    if fallback is not None:
        return reconcile_admin_notification_plan(message, fallback)

    return reconcile_admin_notification_plan(
        message,
        {
            "task_type": "notifications_query",
            "assistant_intro": "",
            "answers": {"mode": "list", "section": "all", "status": "all", "limit": 15},
            "ready_to_execute": True,
            "needs_clarification": False,
            "clarification_question": "",
        },
    )


def try_admin_notifications_turn(
    db: Session,
    admin: User,
    session,
    message: str,
    user_msg_id: int,
    ui_language: str | None,
) -> dict[str, Any] | None:
    """Notifications admin : Phase 5 sur plateforme, liste par défaut, jamais None si workspace."""
    with _platform_notification_backend():
        plan = _resolve_plan(db, admin, session, message, user_msg_id, ui_language)
        if plan is None:
            return None
        turn = _execute_plan(
            db, admin, session, plan, message, ui_language=ui_language
        )
    return _tag_admin_turn(turn)
