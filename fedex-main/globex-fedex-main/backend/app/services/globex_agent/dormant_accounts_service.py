"""Détection des comptes utilisateurs inactifs (comptes dormants)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.user import User, UserRole, UserStatus
from app.models.user_session import UserSession

_DEFAULT_DORMANT_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _last_activity_at(db: Session, user_id: int, *, account_created: datetime) -> datetime:
    log_ts = db.scalar(
        select(func.max(ActivityLog.created_at)).where(
            or_(ActivityLog.user_id == user_id, ActivityLog.actor_user_id == user_id),
        ),
    )
    sess_ts = db.scalar(
        select(func.max(UserSession.updated_at)).where(UserSession.user_id == user_id),
    )
    candidates = [_aware(log_ts), _aware(sess_ts), _aware(account_created)]
    return max(c for c in candidates if c is not None)


def scan_dormant_accounts(
    db: Session,
    *,
    days: int = _DEFAULT_DORMANT_DAYS,
    limit: int = 20,
    role: str | None = None,
) -> list[dict[str, Any]]:
    """Comptes actifs sans activité depuis `days` jours (hors admins)."""
    days = max(int(days or _DEFAULT_DORMANT_DAYS), 7)
    limit = min(max(int(limit or 20), 1), 100)
    cutoff = _now() - timedelta(days=days)

    stmt = (
        select(User)
        .where(
            User.status == UserStatus.active.value,
            User.role != UserRole.admin.value,
        )
        .order_by(User.created_at.asc())
    )
    if role:
        stmt = stmt.where(User.role == role.lower().strip())

    users = list(db.scalars(stmt).all())
    out: list[dict[str, Any]] = []
    for user in users:
        last_at = _last_activity_at(db, user.id, account_created=user.created_at)
        if last_at >= cutoff:
            continue
        inactive_days = max(0, int((_now() - last_at).total_seconds() // 86400))
        out.append(
            {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name or "",
                "role": user.role,
                "status": user.status,
                "last_activity_at": last_at.isoformat(),
                "days_inactive": inactive_days,
                "dormant_days_threshold": days,
            },
        )

    out.sort(key=lambda row: row["days_inactive"], reverse=True)
    return out[:limit]


def dormant_summary_lines(db: Session, *, days: int = _DEFAULT_DORMANT_DAYS) -> list[str]:
    rows = scan_dormant_accounts(db, days=days, limit=5)
    if not rows:
        return []
    lines = [f"Comptes inactifs (>{days}j) : {len(rows)} signalé(s)"]
    for row in rows[:3]:
        name = (row.get("full_name") or row.get("email") or "").strip()
        lines.append(f"  · {name} — {row['days_inactive']}j sans activité")
    return lines
