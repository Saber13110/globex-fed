from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.tracking_request import TrackingRequest
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.tracking import HistoryItem

router = APIRouter(tags=["history"])


def _resolve_session_id(db: Session, user: User, row: TrackingRequest) -> int | None:
    if row.session_id is not None:
        return row.session_id
    stmt = (
        select(ChatMessage.session_id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatSession.user_id == user.id,
            ChatMessage.message_text == row.user_question,
            ChatMessage.sender == "user",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


@router.get("/history", response_model=list[HistoryItem])
def list_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[HistoryItem]:
    stmt = (
        select(TrackingRequest)
        .where(TrackingRequest.user_id == user.id)
        .order_by(TrackingRequest.created_at.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt).all())
    return [
        HistoryItem(
            id=row.id,
            session_id=_resolve_session_id(db, user, row),
            tracking_number=row.tracking_number,
            user_question=row.user_question,
            bot_response=row.bot_response,
            status=row.status,
            current_location=row.current_location,
            estimated_delivery=row.estimated_delivery,
            created_at=row.created_at,
        )
        for row in rows
    ]
