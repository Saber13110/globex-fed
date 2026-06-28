"""Copilot conversations persistence and helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.copilot_action_log import CopilotActionLog
from app.models.copilot_conversation import CopilotConversation
from app.models.copilot_message import CopilotMessage
from app.schemas.employee import EmployeeCopilotCard


def _now() -> datetime:
    return datetime.now(timezone.utc)


def conversation_group(updated_at: datetime) -> str:
    now = _now()
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_yesterday = start_today - timedelta(days=1)
    start_week = start_today - timedelta(days=7)
    ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    if ts >= start_today:
        return "today"
    if ts >= start_yesterday:
        return "yesterday"
    if ts >= start_week:
        return "week"
    return "older"


def log_copilot_action(
    db: Session,
    *,
    employee_id: int,
    action_type: str,
    target_type: str = "",
    target_id: str = "",
) -> None:
    db.add(
        CopilotActionLog(
            employee_id=employee_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
        )
    )


def create_conversation(db: Session, *, employee_id: int, title: str = "New conversation") -> CopilotConversation:
    row = CopilotConversation(employee_id=employee_id, title=title[:200])
    db.add(row)
    db.flush()
    log_copilot_action(db, employee_id=employee_id, action_type="conversation_create", target_type="conversation", target_id=row.id)
    return row


def list_conversations(db: Session, *, employee_id: int, search: str | None = None) -> list[CopilotConversation]:
    stmt = (
        select(CopilotConversation)
        .options(joinedload(CopilotConversation.messages))
        .where(CopilotConversation.employee_id == employee_id)
        .order_by(CopilotConversation.updated_at.desc())
    )
    rows = list(db.scalars(stmt).unique().all())
    if search:
        q = search.strip().lower()
        filtered: list[CopilotConversation] = []
        for row in rows:
            if q in row.title.lower():
                filtered.append(row)
                continue
            if any(q in (m.content or "").lower() for m in row.messages):
                filtered.append(row)
        return filtered
    return rows


def get_conversation(db: Session, *, employee_id: int, conversation_id: str) -> CopilotConversation | None:
    return db.scalar(
        select(CopilotConversation)
        .options(joinedload(CopilotConversation.messages))
        .where(CopilotConversation.id == conversation_id, CopilotConversation.employee_id == employee_id)
    )


def update_conversation_title(db: Session, *, conv: CopilotConversation, title: str) -> CopilotConversation:
    conv.title = title.strip()[:200] or conv.title
    conv.updated_at = _now()
    return conv


def delete_conversation(db: Session, *, conv: CopilotConversation) -> None:
    db.delete(conv)


def add_message(
    db: Session,
    *,
    conversation: CopilotConversation,
    role: str,
    content: str,
    intent: str = "",
    cards: list[EmployeeCopilotCard] | None = None,
) -> CopilotMessage:
    cards_data = [c.model_dump() for c in (cards or [])]
    row = CopilotMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        intent=intent or "",
        cards_json=json.dumps(cards_data, ensure_ascii=False),
    )
    db.add(row)
    conversation.updated_at = _now()
    if role == "user" and conversation.title == "New conversation":
        conversation.title = content.strip()[:48] or conversation.title
    return row


def parse_cards(raw: str) -> list[dict]:
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def conversation_preview(conv: CopilotConversation) -> str:
    for msg in reversed(conv.messages or []):
        if msg.role == "user":
            return (msg.content or "")[:120]
    return conv.title
