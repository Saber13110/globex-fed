from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client_notification import ClientNotification
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.user_notifications import UserNotificationListResponse, UserNotificationRead
from app.services.user_notification_service import notification_to_dict

router = APIRouter(prefix="/notifications", tags=["user-notifications"])


def _to_read(row: ClientNotification) -> UserNotificationRead:
    return UserNotificationRead.model_validate(notification_to_dict(row))


@router.get("/me", response_model=UserNotificationListResponse)
def list_my_notifications(
    type: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, max_length=16),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserNotificationListResponse:
    stmt = select(ClientNotification).where(ClientNotification.user_id == current_user.id)
    if (type):
        if type == "support":
            stmt = stmt.where(ClientNotification.kind.in_(("admin_reply", "support_message")))
        elif type == "documents":
            stmt = stmt.where(ClientNotification.kind.in_(("document_ready", "export_ready")))
        else:
            stmt = stmt.where(ClientNotification.kind == type)
    if status == "unread":
        stmt = stmt.where(ClientNotification.is_read.is_(False))
    elif status == "read":
        stmt = stmt.where(ClientNotification.is_read.is_(True))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(ClientNotification.title).like(like),
                func.lower(ClientNotification.message).like(like),
            )
        )
    stmt = stmt.order_by(ClientNotification.created_at.desc()).limit(limit)
    rows = list(db.scalars(stmt).all())
    unread = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == current_user.id, ClientNotification.is_read.is_(False))
        )
        or 0
    )
    total = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == current_user.id)
        )
        or 0
    )
    return UserNotificationListResponse(
        items=[_to_read(r) for r in rows],
        unread_count=unread,
        total=total,
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
    return _to_read(row)


@router.patch("/read-all")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(ClientNotification).where(
                ClientNotification.user_id == current_user.id,
                ClientNotification.is_read.is_(False),
            )
        ).all()
    )
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return {"updated": len(rows)}


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
