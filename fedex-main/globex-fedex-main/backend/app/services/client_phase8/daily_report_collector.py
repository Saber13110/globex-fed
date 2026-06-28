"""Agrégation déterministe des faits pour le rapport quotidien client."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.shipment_watch import ShipmentWatch
from app.models.tracking_request import TrackingRequest
from app.models.user import User
from app.schemas.user_notifications import UserNotificationRead
from app.services.client_phase4.session_service import list_user_sessions
from app.services.client_phase5.notification_filters import NotificationQueryParams
from app.services.client_phase5.notification_service import fetch_notifications_for_query
from app.services.quota_service import get_daily_usage


def _status_bucket(status: str | None) -> str:
    s = (status or "").lower()
    if any(x in s for x in ("deliver", "livré", "livre")):
        return "delivered"
    if any(x in s for x in ("exception", "incident", "fail", "échec")):
        return "exception"
    if any(x in s for x in ("delay", "retard", "late")):
        return "delayed"
    if any(x in s for x in ("transit", "route", "ship")):
        return "in_transit"
    return "other"


_STATUS_LABELS = {
    "fr": {
        "delivered": "Livré",
        "exception": "Exception",
        "delayed": "Retard",
        "in_transit": "En transit",
        "other": "Autre",
    },
    "en": {
        "delivered": "Delivered",
        "exception": "Exception",
        "delayed": "Delayed",
        "in_transit": "In transit",
        "other": "Other",
    },
}


@dataclass
class DailyReportSnapshot:
    user_id: int
    user_name: str
    user_email: str
    lang: str
    timezone: str
    period_start_local: datetime
    period_end_local: datetime
    generated_at_local: datetime
    kpi_messages: int = 0
    kpi_trackings: int = 0
    kpi_exports: int = 0
    kpi_watches: int = 0
    kpi_unread_notifications: int = 0
    kpi_sessions_today: int = 0
    hourly_activity: dict[int, int] = field(default_factory=dict)
    shipment_status_counts: dict[str, int] = field(default_factory=dict)
    notification_type_counts: dict[str, int] = field(default_factory=dict)
    shipments_today: list[dict[str, Any]] = field(default_factory=list)
    exports_today: list[dict[str, Any]] = field(default_factory=list)
    watches_today: list[dict[str, Any]] = field(default_factory=list)
    sessions_today: list[dict[str, Any]] = field(default_factory=list)
    unread_notifications: list[UserNotificationRead] = field(default_factory=list)
    important_notifications: list[UserNotificationRead] = field(default_factory=list)
    notifications_today: list[UserNotificationRead] = field(default_factory=list)

    def kpi_dict(self) -> dict[str, int]:
        return {
            "messages": self.kpi_messages,
            "trackings": self.kpi_trackings,
            "exports": self.kpi_exports,
            "watches": self.kpi_watches,
            "unread_notifications": self.kpi_unread_notifications,
            "sessions": self.kpi_sessions_today,
        }

    def facts_transcript(self) -> str:
        lines = [
            f"Messages chat: {self.kpi_messages}",
            f"Colis suivis: {self.kpi_trackings}",
            f"Exports: {self.kpi_exports}",
            f"Surveillances: {self.kpi_watches}",
            f"Notifications non lues: {self.kpi_unread_notifications}",
            f"Sessions chat actives aujourd'hui: {self.kpi_sessions_today}",
        ]
        for n in self.important_notifications[:8]:
            lines.append(f"Alerte importante: {n.title} ({n.type})")
        for n in self.unread_notifications[:8]:
            lines.append(f"Non lue: {n.title}")
        return "\n".join(lines)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _start_of_utc_day() -> datetime:
    now = _utc_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _utc_hour(dt: datetime | None) -> int | None:
    ref = _as_utc(dt)
    if ref is None:
        return None
    return ref.hour


def _utc_time_str(dt: datetime | None) -> str:
    ref = _as_utc(dt)
    return ref.strftime("%H:%M") if ref else ""


def _is_important_notification(item: UserNotificationRead) -> bool:
    pr = (item.priority or "").lower()
    if pr in {"high", "urgent", "critical"}:
        return True
    kind = (item.type or "").lower()
    if kind in {"security_alert", "tracking_update"}:
        return True
    msg = (item.message or "").lower()
    if kind == "tracking_update" and any(w in msg for w in ("retard", "delay", "exception")):
        return True
    return False


def collect_daily_report(
    db: Session,
    user: User,
    *,
    lang: str = "fr",
) -> DailyReportSnapshot:
    since_utc = _start_of_utc_day()
    until_utc = _utc_now()
    start_period = since_utc
    end_period = until_utc

    usage = get_daily_usage(db, user.id)
    hourly: dict[int, int] = {h: 0 for h in range(24)}

    msg_rows = list(
        db.scalars(
            select(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                ChatSession.user_id == user.id,
                ChatMessage.sender == MessageSender.user.value,
                ChatMessage.created_at >= since_utc,
                ChatMessage.created_at <= until_utc,
            )
        ).all()
    )
    for row in msg_rows:
        h = _utc_hour(row.created_at)
        if h is not None:
            hourly[h] = hourly.get(h, 0) + 1

    tracking_rows = list(
        db.scalars(
            select(TrackingRequest)
            .where(
                TrackingRequest.user_id == user.id,
                TrackingRequest.created_at >= since_utc,
                TrackingRequest.created_at <= until_utc,
            )
            .order_by(TrackingRequest.created_at.desc())
        ).all()
    )
    for row in tracking_rows:
        h = _utc_hour(row.created_at)
        if h is not None:
            hourly[h] = hourly.get(h, 0) + 1

    status_counts: dict[str, int] = {}
    shipments: list[dict[str, Any]] = []
    seen_tn: set[str] = set()
    for row in tracking_rows:
        tn = row.tracking_number
        if tn in seen_tn:
            continue
        seen_tn.add(tn)
        bucket = _status_bucket(row.status)
        status_counts[bucket] = status_counts.get(bucket, 0) + 1
        shipments.append(
            {
                "tracking_number": tn,
                "status": row.status or "-",
                "location": row.current_location or "-",
                "time": _utc_time_str(row.created_at),
            }
        )

    export_logs = list(
        db.scalars(
            select(ActivityLog)
            .where(
                or_(ActivityLog.user_id == user.id, ActivityLog.actor_user_id == user.id),
                ActivityLog.created_at >= since_utc,
                ActivityLog.created_at <= until_utc,
                ActivityLog.action.like("export.%"),
            )
            .order_by(ActivityLog.created_at.desc())
        ).all()
    )
    exports: list[dict[str, Any]] = []
    for row in export_logs:
        exports.append(
            {
                "action": row.action,
                "message": (row.message or "")[:120],
                "time": _utc_time_str(row.created_at),
            }
        )

    watch_rows = list(
        db.scalars(
            select(ShipmentWatch)
            .where(
                ShipmentWatch.user_id == user.id,
                ShipmentWatch.created_at >= since_utc,
                ShipmentWatch.created_at <= until_utc,
            )
            .order_by(ShipmentWatch.created_at.desc())
        ).all()
    )
    watches: list[dict[str, Any]] = []
    for row in watch_rows:
        watches.append(
            {
                "tracking_number": row.tracking_number,
                "alert_type": row.alert_type or "all",
                "time": _utc_time_str(row.created_at),
            }
        )

    sessions_all = list_user_sessions(db, user_id=user.id, limit=30)
    sessions_today: list[dict[str, Any]] = []
    for sess in sessions_all:
        ref = _as_utc(sess.updated_at or sess.created_at)
        if ref is None:
            continue
        if since_utc <= ref <= until_utc:
            sessions_today.append(
                {
                    "title": (sess.title or "Conversation")[:80],
                    "updated": ref.strftime("%H:%M"),
                }
            )

    unread_result = fetch_notifications_for_query(
        db,
        user.id,
        NotificationQueryParams(mode="list", status="unread", limit=30),
    )
    unread_items = unread_result.items

    today_notifs = fetch_notifications_for_query(
        db,
        user.id,
        NotificationQueryParams(mode="list", since_days=1, limit=50),
    )
    notif_type_counts: dict[str, int] = {}
    for item in today_notifs.items:
        kind = item.type or "other"
        notif_type_counts[kind] = notif_type_counts.get(kind, 0) + 1

    important: list[UserNotificationRead] = []
    for item in unread_items + today_notifs.items:
        if _is_important_notification(item):
            if not any(x.id == item.id for x in important):
                important.append(item)

    return DailyReportSnapshot(
        user_id=user.id,
        user_name=(user.full_name or user.email or "Client").strip(),
        user_email=(user.email or "").strip(),
        lang=lang if lang in {"fr", "en"} else "fr",
        timezone="UTC",
        period_start_local=start_period,
        period_end_local=end_period,
        generated_at_local=end_period,
        kpi_messages=usage.get("messages_today", len(msg_rows)),
        kpi_trackings=usage.get("trackings_today", len(tracking_rows)),
        kpi_exports=usage.get("exports_today", len(export_logs)),
        kpi_watches=len(watch_rows),
        kpi_unread_notifications=unread_result.unread_count,
        kpi_sessions_today=len(sessions_today),
        hourly_activity=hourly,
        shipment_status_counts=status_counts,
        notification_type_counts=notif_type_counts,
        shipments_today=shipments[:25],
        exports_today=exports[:20],
        watches_today=watches[:15],
        sessions_today=sessions_today[:15],
        unread_notifications=unread_items[:30],
        important_notifications=important[:20],
        notifications_today=today_notifs.items[:30],
    )
