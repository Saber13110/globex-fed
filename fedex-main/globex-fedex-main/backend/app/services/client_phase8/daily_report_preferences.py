"""Préférences utilisateur — rapport quotidien planifié (dormant)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.user_daily_report_settings import UserDailyReportSettings

_TIME_RE = re.compile(r"\b(\d{1,2})[:hH\.](\d{2})?\b")


def parse_run_time(message: str) -> str | None:
    """Extrait HH:MM depuis un message (ex. « à 18h », « 18:30 »)."""
    text = (message or "").strip()
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour = min(max(int(m.group(1)), 0), 23)
    minute = int(m.group(2) or 0)
    minute = min(max(minute, 0), 59)
    return f"{hour:02d}:{minute:02d}"


def get_settings_row(db: Session, user_id: int) -> UserDailyReportSettings:
    row = db.get(UserDailyReportSettings, user_id)
    if row is None:
        row = UserDailyReportSettings(user_id=user_id)
        db.add(row)
        db.flush()
    return row


def configure_schedule(
    db: Session,
    user_id: int,
    *,
    run_time: str,
    timezone_name: str | None = None,
) -> UserDailyReportSettings:
    row = get_settings_row(db, user_id)
    row.enabled = True
    row.run_time = run_time
    if timezone_name:
        row.timezone = timezone_name
    else:
        row.timezone = "UTC"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def disable_schedule(db: Session, user_id: int) -> UserDailyReportSettings:
    row = get_settings_row(db, user_id)
    row.enabled = False
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def mark_sent_today(db: Session, user_id: int, *, local_date: date) -> None:
    row = get_settings_row(db, user_id)
    row.last_sent_local_date = local_date
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


def local_now(_tz_name: str | None = None) -> datetime:
    """Heure courante UTC (scheduler dormant)."""
    return datetime.now(timezone.utc)


def start_of_local_day(_tz_name: str | None = None) -> datetime:
    """Début de journée UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def utc_range_for_local_day(_tz_name: str | None = None) -> tuple[datetime, datetime]:
    """Retourne (since_utc, until_utc) pour la journée UTC en cours."""
    now = datetime.now(timezone.utc)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return since, now
