"""Persistance sessions Agent Window (PostgreSQL)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin_fedex_v0_message import Adminfedex-v0Message
from app.models.admin_fedex_v0_session import Adminfedex-v0Session
from app.models.user import User
from app.schemas.agent_window import (
    AgentWindowMessageRead,
    AgentWindowSessionDetail,
    AgentWindowSessionRead,
)


def get_session(db: Session, session_id: str, admin_id: int) -> Adminfedex-v0Session | None:
    return db.scalar(
        select(Adminfedex-v0Session).where(
            Adminfedex-v0Session.id == session_id,
            Adminfedex-v0Session.admin_user_id == admin_id,
            Adminfedex-v0Session.is_archived.is_(False),
        )
    )


def create_session(db: Session, admin: User, *, title: str | None = None) -> Adminfedex-v0Session:
    row = Adminfedex-v0Session(
        admin_user_id=admin.id,
        title=(title or "Nouvelle conversation")[:200],
    )
    db.add(row)
    db.flush()
    return row


def list_sessions(db: Session, admin_id: int, *, limit: int = 30) -> list[AgentWindowSessionRead]:
    rows = list(
        db.scalars(
            select(Adminfedex-v0Session)
            .where(
                Adminfedex-v0Session.admin_user_id == admin_id,
                Adminfedex-v0Session.is_archived.is_(False),
            )
            .order_by(Adminfedex-v0Session.updated_at.desc())
            .limit(limit)
        ).all()
    )
    out: list[AgentWindowSessionRead] = []
    for row in rows:
        count = int(
            db.scalar(
                select(func.count())
                .select_from(Adminfedex-v0Message)
                .where(Adminfedex-v0Message.session_id == row.id)
            )
            or 0
        )
        out.append(
            AgentWindowSessionRead(
                id=row.id,
                title=row.title,
                fedex_v0_session_id=row.fedex_v0_session_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                message_count=count,
            )
        )
    return out


def get_session_detail(db: Session, session_id: str, admin_id: int) -> AgentWindowSessionDetail | None:
    row = get_session(db, session_id, admin_id)
    if row is None:
        return None
    messages = list(
        db.scalars(
            select(Adminfedex-v0Message)
            .where(Adminfedex-v0Message.session_id == row.id)
            .order_by(Adminfedex-v0Message.created_at)
        ).all()
    )
    count = len(messages)
    return AgentWindowSessionDetail(
        session=AgentWindowSessionRead(
            id=row.id,
            title=row.title,
            fedex_v0_session_id=row.fedex_v0_session_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            message_count=count,
        ),
        messages=[
            AgentWindowMessageRead(
                id=m.id,
                sender=m.sender,
                message_text=m.message_text,
                created_at=m.created_at,
                latency_ms=m.latency_ms,
            )
            for m in messages
        ],
    )


def append_message(
    db: Session,
    session: Adminfedex-v0Session,
    *,
    sender: str,
    message_text: str,
    latency_ms: float | None = None,
    fedex_v0_route: str = "",
) -> Adminfedex-v0Message:
    msg = Adminfedex-v0Message(
        session_id=session.id,
        sender=sender,
        message_text=message_text,
        latency_ms=latency_ms,
        fedex_v0_route=fedex_v0_route,
    )
    db.add(msg)
    if sender == "admin" and session.title == "Nouvelle conversation":
        session.title = message_text.strip()[:48] or session.title
    db.flush()
    return msg


def archive_session(db: Session, session_id: str, admin_id: int) -> bool:
    row = get_session(db, session_id, admin_id)
    if row is None:
        return False
    row.is_archived = True
    db.flush()
    return True
