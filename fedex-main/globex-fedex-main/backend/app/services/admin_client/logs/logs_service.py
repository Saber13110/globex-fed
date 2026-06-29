"""Façade métier journaux d'activité admin — PostgreSQL."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.user import User
from app.schemas.admin import ActivityLogListResponse, ActivityLogRead
from app.services.admin_client.logs.logs_types import LogsToolError
from app.services.admin_logs_export_service import parse_log_period_hours

_VALID_LEVELS = frozenset({"INFO", "WARNING", "ERROR", "DEBUG"})
_VALID_CATEGORIES = frozenset({
    "system", "admin", "chat", "security", "auth", "user", "employee", "support",
})


def _users_by_id(db: Session, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids))).all()
    return {u.id: u for u in rows}


def _log_to_dict(row: ActivityLog, users_map: dict[int, User]) -> dict[str, Any]:
    subject = users_map.get(row.user_id) if row.user_id else None
    actor = users_map.get(row.actor_user_id) if row.actor_user_id else None
    return {
        "id": row.id,
        "user_id": row.user_id,
        "actor_user_id": row.actor_user_id,
        "user_email": subject.email if subject else None,
        "user_name": subject.full_name if subject else None,
        "actor_email": actor.email if actor else None,
        "level": row.level,
        "category": row.category,
        "action": row.action,
        "message": row.message,
        "metadata_json": row.metadata_json,
        "ip_address": row.ip_address,
        "created_at": row.created_at,
    }


def _log_to_read(row: ActivityLog, users_map: dict[int, User]) -> ActivityLogRead:
    d = _log_to_dict(row, users_map)
    return ActivityLogRead(**d)


def _normalize_level(level: str | None) -> str | None:
    lvl = (level or "").strip().upper()
    return lvl if lvl in _VALID_LEVELS else None


def _normalize_category(category: str | None) -> str | None:
    cat = (category or "").strip().lower()
    return cat if cat in _VALID_CATEGORIES else (cat if cat else None)


def _today_start_utc() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_period(
    message: str,
    *,
    period_hours: int | None = None,
    since_today: bool = False,
) -> datetime | None:
    if since_today:
        return _today_start_utc()
    hours = period_hours
    if hours is None and message:
        hours = parse_log_period_hours(message, default=24)
    if hours is None:
        return None
    return datetime.now(timezone.utc) - timedelta(hours=int(hours))


def list_logs_filtered(
    db: Session,
    *,
    user_id: int | None = None,
    actor_id: int | None = None,
    category: str | None = None,
    level: str | None = None,
    action: str | None = None,
    q: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 30,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    limit = min(max(int(limit or 30), 1), 100)
    offset = max(int(offset or 0), 0)

    stmt = select(ActivityLog)
    count_stmt = select(func.count()).select_from(ActivityLog)

    def _apply(s):
        if user_id is not None:
            s = s.where(or_(ActivityLog.user_id == user_id, ActivityLog.actor_user_id == user_id))
        if actor_id is not None:
            s = s.where(ActivityLog.actor_user_id == actor_id)
        cat = _normalize_category(category)
        if cat:
            s = s.where(ActivityLog.category == cat)
        lvl = _normalize_level(level)
        if lvl:
            s = s.where(ActivityLog.level == lvl)
        if action and action.strip():
            act = action.strip()
            s = s.where(ActivityLog.action.ilike(f"%{act}%"))
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            s = s.where(or_(ActivityLog.message.ilike(pattern), ActivityLog.action.ilike(pattern)))
        if since is not None:
            s = s.where(ActivityLog.created_at >= since)
        if until is not None:
            s = s.where(ActivityLog.created_at <= until)
        return s

    stmt = _apply(stmt)
    count_stmt = _apply(count_stmt)
    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    ids: set[int] = set()
    for row in rows:
        if row.user_id:
            ids.add(row.user_id)
        if row.actor_user_id:
            ids.add(row.actor_user_id)
    users_map = _users_by_id(db, ids)
    return [_log_to_dict(r, users_map) for r in rows], total


def get_log_detail(db: Session, log_id: int) -> dict[str, Any]:
    row = db.get(ActivityLog, log_id)
    if row is None:
        raise LogsToolError("log_not_found")
    ids: set[int] = set()
    if row.user_id:
        ids.add(row.user_id)
    if row.actor_user_id:
        ids.add(row.actor_user_id)
    users_map = _users_by_id(db, ids)
    data = _log_to_dict(row, users_map)
    data["metadata"] = parse_log_metadata(row.metadata_json)
    return data


def parse_log_metadata(metadata_json: str | None) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        data = json.loads(metadata_json)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_session_id_from_log(log: dict[str, Any]) -> int | None:
    meta = log.get("metadata")
    if not isinstance(meta, dict):
        meta = parse_log_metadata(log.get("metadata_json"))
    for key in ("session_id", "chat_session_id"):
        raw = meta.get(key)
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
    return None


def resolve_user_id_from_log(log: dict[str, Any]) -> int | None:
    """Utilisateur cible pour action admin — priorité sujet puis acteur."""
    uid = log.get("user_id")
    if uid:
        return int(uid)
    aid = log.get("actor_user_id")
    if aid:
        return int(aid)
    return None


def summarize_user_day(
    db: Session,
    user_id: int,
    *,
    since: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if db.get(User, user_id) is None:
        raise LogsToolError("user_not_found")
    since_dt = since or _today_start_utc()
    logs, total = list_logs_filtered(
        db, user_id=user_id, since=since_dt, limit=limit
    )
    by_level: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_action: dict[str, int] = {}
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in logs:
        lvl = str(row.get("level") or "INFO")
        cat = str(row.get("category") or "system")
        act = str(row.get("action") or "unknown")
        by_level[lvl] = by_level.get(lvl, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1
        by_action[act] = by_action.get(act, 0) + 1
        if lvl == "WARNING":
            warnings.append(row)
        if lvl == "ERROR":
            errors.append(row)
    top_actions = sorted(by_action.items(), key=lambda x: -x[1])[:8]
    user = db.get(User, user_id)
    return {
        "user_id": user_id,
        "user_email": user.email if user else None,
        "user_name": user.full_name if user else None,
        "since": since_dt,
        "total": total,
        "shown": len(logs),
        "by_level": by_level,
        "by_category": by_category,
        "by_action": dict(top_actions),
        "warnings": warnings[:5],
        "errors": errors[:5],
        "logs": logs,
    }


def summarize_platform_day(
    db: Session,
    *,
    since: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    since_dt = since or _today_start_utc()
    logs, total = list_logs_filtered(db, since=since_dt, limit=limit)
    by_level: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_action: dict[str, int] = {}
    active_users: set[int] = set()
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in logs:
        lvl = str(row.get("level") or "INFO")
        cat = str(row.get("category") or "system")
        act = str(row.get("action") or "unknown")
        by_level[lvl] = by_level.get(lvl, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1
        by_action[act] = by_action.get(act, 0) + 1
        uid = row.get("user_id") or row.get("actor_user_id")
        if uid:
            active_users.add(int(uid))
        if lvl == "WARNING":
            warnings.append(row)
        if lvl == "ERROR":
            errors.append(row)
    top_actions = sorted(by_action.items(), key=lambda x: -x[1])[:8]
    return {
        "platform": True,
        "since": since_dt,
        "total": total,
        "shown": len(logs),
        "active_users": len(active_users),
        "by_level": by_level,
        "by_category": by_category,
        "by_action": dict(top_actions),
        "warnings": warnings[:5],
        "errors": errors[:5],
        "logs": logs,
    }


def resolve_user_id_by_email_or_name(db: Session, query: str) -> int | None:
    q = (query or "").strip()
    if not q:
        return None
    if "@" in q:
        user = db.scalar(select(User).where(User.email.ilike(q)).limit(1))
        return user.id if user else None
    pattern = f"%{q}%"
    user = db.scalar(
        select(User)
        .where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
        .limit(1)
    )
    return user.id if user else None
