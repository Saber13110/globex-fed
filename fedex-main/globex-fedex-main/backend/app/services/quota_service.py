"""Quotas journaliers optionnels par utilisateur (définis par l'admin)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole


def _start_of_utc_day() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _is_exempt(user: User) -> bool:
    return user.role == UserRole.admin.value


def get_daily_usage(db: Session, user_id: int) -> dict[str, int]:
    since = _start_of_utc_day()
    messages_today = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                ChatSession.user_id == user_id,
                ChatMessage.sender == MessageSender.user.value,
                ChatMessage.created_at >= since,
            )
        )
        or 0
    )
    trackings_today = int(
        db.scalar(
            select(func.count())
            .select_from(TrackingRequest)
            .where(TrackingRequest.user_id == user_id, TrackingRequest.created_at >= since)
        )
        or 0
    )
    exports_today = int(
        db.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.user_id == user_id,
                ActivityLog.action == "export.tracking_excel",
                ActivityLog.created_at >= since,
            )
        )
        or 0
    )
    return {
        "messages_today": messages_today,
        "trackings_today": trackings_today,
        "exports_today": exports_today,
    }


def build_quota_status(db: Session, user: User) -> dict:
    usage = get_daily_usage(db, user.id)
    limits = {
        "messages_per_day": user.quota_messages_per_day,
        "trackings_per_day": user.quota_trackings_per_day,
        "exports_per_day": user.quota_exports_per_day,
    }

    def remaining(limit_key: str, usage_key: str) -> int | None:
        cap = limits[limit_key]
        if cap is None:
            return None
        return max(0, cap - usage[usage_key])

    return {
        "limits": limits,
        "usage": usage,
        "remaining": {
            "messages_per_day": remaining("messages_per_day", "messages_today"),
            "trackings_per_day": remaining("trackings_per_day", "trackings_today"),
            "exports_per_day": remaining("exports_per_day", "exports_today"),
        },
        "exempt": _is_exempt(user),
    }


def enforce_daily_quota(db: Session, user: User, *, kind: str) -> None:
    """Lève HTTP 429 si le quota journalier est atteint. kind: messages | trackings | exports."""
    if _is_exempt(user):
        return

    usage = get_daily_usage(db, user.id)
    checks = {
        "messages": ("quota_messages_per_day", "messages_today", "messages de chat"),
        "trackings": ("quota_trackings_per_day", "trackings_today", "consultations de suivi"),
        "exports": ("quota_exports_per_day", "exports_today", "exports Excel"),
    }
    if kind not in checks:
        return

    attr, usage_key, label = checks[kind]
    cap = getattr(user, attr)
    if cap is None:
        return
    if usage[usage_key] >= cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Quota journalier atteint pour les {label} ({cap}/jour). "
                "Contactez votre administrateur pour augmenter votre limite."
            ),
        )
