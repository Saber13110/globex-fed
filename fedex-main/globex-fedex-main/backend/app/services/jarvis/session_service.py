"""Persistance sessions Agent Window (PostgreSQL)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin_jarvis_message import AdminJarvisMessage
from app.models.admin_jarvis_session import AdminJarvisSession
from app.models.user import User
from app.schemas.agent_window import (
    AgentWindowMessageRead,
    AgentWindowSessionDetail,
    AgentWindowSessionRead,
)


def get_session(db: Session, session_id: str, admin_id: int) -> AdminJarvisSession | None:
    return db.scalar(
        select(AdminJarvisSession).where(
            AdminJarvisSession.id == session_id,
            AdminJarvisSession.admin_user_id == admin_id,
            AdminJarvisSession.is_archived.is_(False),
        )
    )


def create_session(db: Session, admin: User, *, title: str | None = None) -> AdminJarvisSession:
    row = AdminJarvisSession(
        admin_user_id=admin.id,
        title=(title or "Nouvelle conversation")[:200],
    )
    db.add(row)
    db.flush()
    return row


def list_sessions(db: Session, admin_id: int, *, limit: int = 30) -> list[AgentWindowSessionRead]:
    rows = list(
        db.scalars(
            select(AdminJarvisSession)
            .where(
                AdminJarvisSession.admin_user_id == admin_id,
                AdminJarvisSession.is_archived.is_(False),
            )
            .order_by(AdminJarvisSession.updated_at.desc())
            .limit(limit)
        ).all()
    )
    out: list[AgentWindowSessionRead] = []
    for row in rows:
        count = int(
            db.scalar(
                select(func.count())
                .select_from(AdminJarvisMessage)
                .where(AdminJarvisMessage.session_id == row.id)
            )
            or 0
        )
        out.append(
            AgentWindowSessionRead(
                id=row.id,
                title=row.title,
                jarvis_session_id=row.jarvis_session_id,
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
            select(AdminJarvisMessage)
            .where(AdminJarvisMessage.session_id == row.id)
            .order_by(AdminJarvisMessage.created_at)
        ).all()
    )
    count = len(messages)
    return AgentWindowSessionDetail(
        session=AgentWindowSessionRead(
            id=row.id,
            title=row.title,
            jarvis_session_id=row.jarvis_session_id,
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
    session: AdminJarvisSession,
    *,
    sender: str,
    message_text: str,
    latency_ms: float | None = None,
    jarvis_route: str = "",
) -> AdminJarvisMessage:
    msg = AdminJarvisMessage(
        session_id=session.id,
        sender=sender,
        message_text=message_text,
        latency_ms=latency_ms,
        jarvis_route=jarvis_route,
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
