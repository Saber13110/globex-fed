"""Requêtes PlatformNotification pour le routeur Phase 5 admin."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.platform_notification import PlatformNotification
from app.schemas.user_notifications import UserNotificationListResponse, UserNotificationRead
from app.services.client_phase5.notification_filters import CHAT_LIST_MAX, NotificationQueryParams
from app.services.notifications_service import sync_notifications

_CATEGORY_TO_TYPE = {
    "colis": "tracking_update",
    "ia": "ai_report",
    "incidents": "support_message",
    "system": "system_alert",
    "users": "system_alert",
}


def platform_item_to_user_read(row: PlatformNotification, admin_id: int) -> UserNotificationRead:
    return UserNotificationRead(
        id=row.id,
        user_id=admin_id,
        type=_platform_type(row.category),
        title=row.title,
        message=row.message,
        status="read" if row.is_read else "unread",
        priority=row.priority or "medium",
        related_tracking_number=row.tracking_number or "",
        link=row.route or "/notifications",
        is_read=row.is_read,
        created_at=row.created_at,
        read_at=None,
    )


def _platform_type(category: str) -> str:
    return _CATEGORY_TO_TYPE.get((category or "").lower(), "system_alert")


def _apply_filters(stmt, params: NotificationQueryParams):
    section = (params.section or "all").strip().lower()
    status = (params.status or "all").strip().lower()

    if section == "unread" or status == "unread":
        stmt = stmt.where(PlatformNotification.is_read.is_(False))
    elif status == "read":
        stmt = stmt.where(PlatformNotification.is_read.is_(True))

    if section == "tracking":
        stmt = stmt.where(PlatformNotification.category == "colis")
    elif section == "support":
        stmt = stmt.where(PlatformNotification.category == "incidents")
    elif section == "ai":
        stmt = stmt.where(PlatformNotification.category == "ia")
    elif section == "security":
        stmt = stmt.where(
            or_(
                func.lower(PlatformNotification.title).like("%securite%"),
                func.lower(PlatformNotification.message).like("%securite%"),
                func.lower(PlatformNotification.title).like("%connexion%"),
                func.lower(PlatformNotification.message).like("%connexion%"),
                func.lower(PlatformNotification.title).like("%login%"),
                func.lower(PlatformNotification.message).like("%login%"),
            )
        )
    elif section == "documents":
        stmt = stmt.where(
            or_(
                func.lower(PlatformNotification.title).like("%document%"),
                func.lower(PlatformNotification.message).like("%document%"),
                func.lower(PlatformNotification.title).like("%export%"),
                func.lower(PlatformNotification.message).like("%export%"),
                func.lower(PlatformNotification.title).like("%pod%"),
                func.lower(PlatformNotification.message).like("%pod%"),
                func.lower(PlatformNotification.title).like("%preuve%"),
                func.lower(PlatformNotification.message).like("%preuve%"),
            )
        )

    tn = (params.tracking_number or "").strip()
    if tn:
        stmt = stmt.where(PlatformNotification.tracking_number == tn)

    pr = (params.priority or "all").strip().lower()
    if pr and pr != "all":
        stmt = stmt.where(PlatformNotification.priority == pr)

    q = (params.search_query or params.semantic_topic or "").strip()
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(PlatformNotification.title).like(term),
                func.lower(PlatformNotification.message).like(term),
            )
        )

    if params.since_days is not None and params.since_days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=params.since_days)
        stmt = stmt.where(PlatformNotification.created_at >= since)

    return stmt


def fetch_platform_notifications_for_query(
    db: Session,
    user_id: int,
    params: NotificationQueryParams,
) -> UserNotificationListResponse:
    """Signature compatible avec `client_phase5.notification_service.fetch_notifications_for_query`."""
    sync_notifications(db)

    limit = min(max(int(params.limit or 15), 1), CHAT_LIST_MAX)
    base = select(PlatformNotification).where(PlatformNotification.is_archived.is_(False))
    filtered = _apply_filters(base, params)

    unread = int(
        db.scalar(
            select(func.count())
            .select_from(PlatformNotification)
            .where(
                PlatformNotification.is_archived.is_(False),
                PlatformNotification.is_read.is_(False),
            )
        )
        or 0
    )
    total = int(
        db.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    )
    rows = list(
        db.scalars(
            filtered.order_by(PlatformNotification.created_at.desc()).limit(limit)
        ).all()
    )
    return UserNotificationListResponse(
        items=[platform_item_to_user_read(r, user_id) for r in rows],
        unread_count=unread,
        total=total,
    )


def mark_all_platform_notifications_read(db: Session, user_id: int) -> int:
    """Signature compatible avec `mark_all_user_notifications_read` (user_id ignoré)."""
    del user_id
    from app.services.notifications_service import mark_all_read as _mark_all

    return _mark_all(db)
