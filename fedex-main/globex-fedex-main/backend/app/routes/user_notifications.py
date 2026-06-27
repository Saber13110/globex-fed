from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client_notification import ClientNotification
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.user_notifications import UserNotificationListResponse, UserNotificationRead
from app.services.user_notification_service import (
    list_user_notifications,
    mark_all_user_notifications_read,
    notification_to_read,
)

router = APIRouter(prefix="/notifications", tags=["user-notifications"])


@router.get("/me", response_model=UserNotificationListResponse)
def list_my_notifications(
    type: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, max_length=16),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserNotificationListResponse:
    return list_user_notifications(
        db,
        current_user.id,
        type=type,
        status=status,
        q=q,
        limit=limit,
    )


@router.get("/me/unread-count")
def my_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    count = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == current_user.id, ClientNotification.is_read.is_(False))
        )
        or 0
    )
    return {"count": count}


@router.patch("/{notif_id}/read", response_model=UserNotificationRead)
def mark_notification_read(
    notif_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserNotificationRead:
    row = db.get(ClientNotification, notif_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable.")
    row.is_read = True
    row.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return notification_to_read(row)


@router.patch("/read-all")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    updated = mark_all_user_notifications_read(db, current_user.id)
    return {"updated": updated}


@router.delete("/{notif_id}")
def delete_notification(
    notif_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    row = db.get(ClientNotification, notif_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable.")
    db.delete(row)
    db.commit()
    return {"deleted": True}
