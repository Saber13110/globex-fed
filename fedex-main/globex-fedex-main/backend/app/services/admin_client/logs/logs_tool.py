"""Outils logs admin — délégation service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.admin_client.logs import logs_anomalies, logs_service
from app.services.admin_client.logs.logs_types import LogsPlan


def list_logs(db: Session, plan: LogsPlan) -> dict[str, Any]:
    since = logs_service.resolve_period(
        "",
        period_hours=plan.period_hours,
        since_today=plan.since_today,
    )
    items, total = logs_service.list_logs_filtered(
        db,
        user_id=plan.user_id,
        category=plan.category_filter,
        level=plan.level_filter,
        action=plan.action_filter,
        q=plan.search_query,
        since=since,
        limit=plan.limit,
    )
    return {"logs": items, "total": total}


def get_log_detail(db: Session, log_id: int) -> dict[str, Any]:
    return logs_service.get_log_detail(db, log_id)


def build_platform_day_summary(db: Session, plan: LogsPlan) -> dict[str, Any]:
    since = logs_service.resolve_period(
        "",
        period_hours=None,
        since_today=plan.since_today or True,
    )
    return logs_service.summarize_platform_day(db, since=since, limit=plan.limit)


def build_user_day_summary(db: Session, plan: LogsPlan) -> dict[str, Any]:
    since = logs_service.resolve_period(
        "",
        period_hours=None,
        since_today=plan.since_today or True,
    )
    return logs_service.summarize_user_day(
        db,
        int(plan.user_id),
        since=since,
        limit=plan.limit,
    )


def build_anomalies(db: Session, plan: LogsPlan, *, message: str = "") -> dict[str, Any]:
    hours = plan.period_hours or logs_service.parse_log_period_hours(message, default=24)
    since = logs_service.resolve_period("", period_hours=hours)
    logs, _ = logs_service.list_logs_filtered(db, since=since, limit=200)
    return logs_anomalies.analyze_logs(logs, hours=hours)
