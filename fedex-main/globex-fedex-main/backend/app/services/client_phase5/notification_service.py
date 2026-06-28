"""Requêtes notifications client pour Phase 5."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.user_notifications import UserNotificationListResponse
from app.services.client_phase5.notification_filters import (
    NotificationQueryParams,
    section_to_api_type,
)
from app.services.user_notification_service import list_user_notifications


def fetch_notifications_for_query(
    db: Session,
    user_id: int,
    params: NotificationQueryParams,
) -> UserNotificationListResponse:
    api_type = section_to_api_type(params.section)
    status = params.status
    if params.section == "unread" and status == "all":
        status = "unread"
    q = params.search_query or params.semantic_topic or None
    return list_user_notifications(
        db,
        user_id,
        type=api_type,
        status=status if status != "all" else None,
        q=q,
        limit=params.limit,
        tracking_number=params.tracking_number or None,
        priority=params.priority if params.priority != "all" else None,
        since_days=params.since_days,
    )
