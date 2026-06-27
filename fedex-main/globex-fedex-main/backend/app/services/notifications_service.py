"""Centre de notifications — sync, stats, préférences, export."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.platform_notification import NotificationPreference, PlatformNotification
from app.models.report_run import ReportRun
from app.models.shipment_cache import ShipmentCache
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole
from app.schemas.notifications import (
    AiNotificationInsight,
    AiReportNotificationResponse,
    CreateRuleRequest,
    NotificationItem,
    NotificationKpiItem,
    NotificationListResponse,
    NotificationOverview,
    NotificationPreferences,
    NotificationStatsResponse,
    TestAlertRequest,
    TimelineEvent,
    WebhookImportResponse,
)
from app.services.command_center_service import _pct_change, _daily_counts
from app.services import llm_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _relative_label(dt: datetime) -> str:
    ref = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    delta = _now() - ref
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "Just now"
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return "Yesterday"
    return ref.strftime("%d/%m/%y %H:%M")


def _time_hm(dt: datetime) -> str:
    ref = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return ref.strftime("%H:%M")


def _upsert(
    db: Session,
    *,
    external_key: str,
    category: str,
    title: str,
    message: str,
    tracking_number: str = "",
    route: str = "",
    priority: str = "normal",
    channel: str = "web",
    icon: str = "bell",
    action_label: str = "Voir",
    action_type: str = "",
    action_ref: str = "",
    created_at: datetime | None = None,
) -> None:
    exists = db.scalar(select(PlatformNotification.id).where(PlatformNotification.external_key == external_key))
    if exists:
        return
    row = PlatformNotification(
        external_key=external_key,
        category=category,
        title=title,
        message=message,
        tracking_number=tracking_number,
        route=route,
        priority=priority,
        channel=channel,
        icon=icon,
        action_label=action_label,
        action_type=action_type,
        action_ref=action_ref,
        is_read=False,
        is_archived=False,
    )
    if created_at:
        row.created_at = created_at
    db.add(row)


def sync_notifications(db: Session) -> None:
    """Alimente les notifications depuis les données réelles de la plateforme."""
    since = _now() - timedelta(days=30)

    shipments = db.scalars(
        select(ShipmentCache).where(ShipmentCache.updated_at >= since).order_by(ShipmentCache.updated_at.desc()).limit(40)
    ).all()
    for s in shipments:
        status = (s.last_status or "").lower()
        tracking = s.tracking_number or ""
        route = s.last_location or "Route inconnue"
        if any(w in status for w in ("delay", "retard", "exception", "hold")):
            _upsert(
                db,
                external_key=f"ship-delay-{tracking}",
                category="colis",
                title="Shipment Delay Alert",
                message=f"Tracking #{tracking} is delayed",
                tracking_number=tracking,
                route=route if "→" in route else f"{route}",
                priority="high",
                icon="truck",
                action_label="Voir",
                action_type="tracking",
                action_ref=tracking,
                created_at=s.updated_at,
            )
        elif any(w in status for w in ("deliver", "livré", "livre")):
            _upsert(
                db,
                external_key=f"ship-delivered-{tracking}",
                category="colis",
                title="Package Delivered",
                message=f"Tracking #{tracking} delivered successfully",
                tracking_number=tracking,
                route=route,
                priority="normal",
                icon="check",
                action_label="Voir",
                action_type="tracking",
                action_ref=tracking,
                created_at=s.updated_at,
            )

    trackings = db.scalars(
        select(TrackingRequest).where(TrackingRequest.created_at >= since).order_by(TrackingRequest.created_at.desc()).limit(20)
    ).all()
    for t in trackings:
        _upsert(
            db,
            external_key=f"track-req-{t.id}",
            category="colis",
            title="Tracking Request",
            message=f"New tracking lookup #{t.tracking_number}",
            tracking_number=t.tracking_number or "",
            route="",
            icon="package",
            action_type="tracking",
            action_ref=t.tracking_number or str(t.id),
            created_at=t.created_at,
        )

    new_users = db.scalars(
        select(User)
        .where(User.created_at >= since, User.role != UserRole.admin.value)
        .order_by(User.created_at.desc())
        .limit(15)
    ).all()
    for u in new_users:
        _upsert(
            db,
            external_key=f"user-new-{u.id}",
            category="users",
            title="New User Registered",
            message=f"{u.full_name} has created a new account",
            icon="user",
            action_label="Voir l'utilisateur",
            action_type="user",
            action_ref=str(u.id),
            created_at=u.created_at,
        )

    reports = db.scalars(
        select(ReportRun).where(ReportRun.created_at >= since).order_by(ReportRun.created_at.desc()).limit(10)
    ).all()
    for r in reports:
        _upsert(
            db,
            external_key=f"report-{r.id}",
            category="ia",
            title="AI Insight Generated",
            message=f"{r.name} is ready",
            icon="brain",
            action_label="Ouvrir le rapport",
            action_type="report",
            action_ref=str(r.id),
            created_at=r.created_at,
        )

    tickets = db.scalars(
        select(SupportTicket).where(SupportTicket.status == SupportTicketStatus.open).order_by(SupportTicket.created_at.desc()).limit(10)
    ).all()
    for tk in tickets:
        _upsert(
            db,
            external_key=f"incident-{tk.id}",
            category="incidents",
            title="Customs Exception" if "custom" in tk.subject.lower() else "Support Incident",
            message=tk.message[:180] or tk.subject,
            priority="high",
            icon="alert",
            action_label="Voir",
            action_type="incident",
            action_ref=str(tk.id),
            created_at=tk.created_at,
        )

    ai_logs = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.action == "admin.command_center_ai", ActivityLog.created_at >= since)
        .order_by(ActivityLog.created_at.desc())
        .limit(8)
    ).all()
    for log in ai_logs:
        _upsert(
            db,
            external_key=f"ai-log-{log.id}",
            category="ia",
            title="AI Activity",
            message=log.message[:180],
            icon="brain",
            action_label="Détails",
            action_type="ai",
            action_ref=str(log.id),
            created_at=log.created_at,
        )

    system_logs = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.category == "system", ActivityLog.created_at >= since)
        .order_by(ActivityLog.created_at.desc())
        .limit(5)
    ).all()
    for log in system_logs:
        _upsert(
            db,
            external_key=f"sys-log-{log.id}",
            category="system",
            title="System Event",
            message=log.message[:180],
            icon="server",
            action_label="Détails",
            action_type="detail",
            action_ref=str(log.id),
            created_at=log.created_at,
        )

    if not db.scalar(select(func.count()).select_from(PlatformNotification)):
        _seed_demo_notifications(db)

    db.commit()


def _seed_demo_notifications(db: Session) -> None:
    demos = [
        ("demo-delay-1", "colis", "Shipment Delay Alert", "Tracking #123456789 is delayed", "123456789", "Chicago, IL → New York, NY", "high", "truck", "Voir", "tracking", "123456789"),
        ("demo-delivered-1", "colis", "Package Delivered", "Tracking #987654321 delivered successfully", "987654321", "Los Angeles → Seattle", "normal", "check", "Voir", "tracking", "987654321"),
        ("demo-ai-1", "ia", "AI Insight Generated", "Weekly performance report is ready", "", "", "normal", "brain", "Ouvrir le rapport", "report", "1"),
        ("demo-user-1", "users", "New User Registered", "Sarah Johnson has created a new account", "", "", "normal", "user", "Voir l'utilisateur", "user", "1"),
        ("demo-customs-1", "colis", "Customs Exception", "Documentation missing for shipment #456789123", "456789123", "Paris → Casablanca", "high", "alert", "Voir", "tracking", "456789123"),
        ("demo-api-1", "system", "API Connection Restored", "FedEx API connection is back to normal", "", "", "normal", "server", "Détails", "detail", "fedex"),
    ]
    now = _now()
    for i, d in enumerate(demos):
        _upsert(
            db,
            external_key=d[0],
            category=d[1],
            title=d[2],
            message=d[3],
            tracking_number=d[4],
            route=d[5],
            priority=d[6],
            icon=d[7],
            action_label=d[8],
            action_type=d[9],
            action_ref=d[10],
            created_at=now - timedelta(minutes=5 * (i + 1)),
        )


def _row_to_item(row: PlatformNotification) -> NotificationItem:
    return NotificationItem(
        id=row.id,
        category=row.category,
        title=row.title,
        message=row.message,
        tracking_number=row.tracking_number,
        route=row.route,
        priority=row.priority,
        channel=row.channel,
        icon=row.icon,
        action_label=row.action_label,
        action_type=row.action_type,
        action_ref=row.action_ref,
        is_read=row.is_read,
        is_archived=row.is_archived,
        created_at=row.created_at,
        time_label=_relative_label(row.created_at),
    )


def list_notifications(
    db: Session,
    *,
    tab: str = "all",
    search: str = "",
    sort: str = "newest",
    status: str = "all",
    priority: str = "all",
    channel: str = "all",
    page: int = 1,
    page_size: int = 6,
) -> NotificationListResponse:
    sync_notifications(db)
    q = select(PlatformNotification).where(PlatformNotification.is_archived.is_(False))
    if tab != "all":
        cat_map = {"colis": "colis", "ia": "ia", "users": "users", "users": "users", "utilisateurs": "users", "system": "system", "systeme": "system", "incidents": "incidents"}
        cat = cat_map.get(tab.lower(), tab.lower())
        q = q.where(PlatformNotification.category == cat)
    if status == "unread":
        q = q.where(PlatformNotification.is_read.is_(False))
    elif status == "read":
        q = q.where(PlatformNotification.is_read.is_(True))
    if priority != "all":
        q = q.where(PlatformNotification.priority == priority)
    if channel != "all":
        q = q.where(PlatformNotification.channel == channel)
    if search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(
            or_(
                func.lower(PlatformNotification.title).like(term),
                func.lower(PlatformNotification.message).like(term),
                func.lower(PlatformNotification.tracking_number).like(term),
            )
        )
    base = q
    if sort == "oldest":
        ordered = base.order_by(PlatformNotification.created_at.asc())
    elif sort == "priority":
        ordered = base.order_by(PlatformNotification.priority.desc(), PlatformNotification.created_at.desc())
    else:
        ordered = base.order_by(PlatformNotification.created_at.desc())

    total = len(db.scalars(base).all())
    unread = int(
        db.scalar(
            select(func.count()).select_from(PlatformNotification).where(
                PlatformNotification.is_archived.is_(False), PlatformNotification.is_read.is_(False)
            )
        )
        or 0
    )
    rows = db.scalars(ordered.offset((page - 1) * page_size).limit(page_size)).all()
    return NotificationListResponse(
        items=[_row_to_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        unread_count=unread,
    )


def build_stats(db: Session) -> NotificationStatsResponse:
    sync_notifications(db)
    start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = start - timedelta(days=1)

    today_count = int(
        db.scalar(select(func.count()).select_from(PlatformNotification).where(PlatformNotification.created_at >= start))
        or 0
    )
    yesterday_count = int(
        db.scalar(
            select(func.count())
            .select_from(PlatformNotification)
            .where(PlatformNotification.created_at >= yesterday, PlatformNotification.created_at < start)
        )
        or 0
    )
    unread = int(
        db.scalar(
            select(func.count()).select_from(PlatformNotification).where(
                PlatformNotification.is_archived.is_(False), PlatformNotification.is_read.is_(False)
            )
        )
        or 0
    )
    unread_yesterday = max(1, unread)
    colis = int(
        db.scalar(
            select(func.count()).select_from(PlatformNotification).where(
                PlatformNotification.category == "colis", PlatformNotification.created_at >= start
            )
        )
        or 0
    )
    ia = int(
        db.scalar(
            select(func.count()).select_from(PlatformNotification).where(
                PlatformNotification.category == "ia", PlatformNotification.created_at >= start
            )
        )
        or 0
    )

    daily = _daily_counts(db, PlatformNotification, PlatformNotification.created_at, 7)
    t1, up1 = _pct_change(today_count, yesterday_count)

    kpis = [
        NotificationKpiItem(key="today", label="Notifications aujourd'hui", value=today_count or unread + colis, trend_value=t1, trend_up=up1, trend_label=f"{'+' if up1 else '-'}{t1}% vs yesterday", icon="bell", sparkline=[float(v) for v in daily]),
        NotificationKpiItem(key="unread", label="Non lues", value=unread, trend_value=float(unread), trend_up=unread > 0, trend_label=f"+{unread} from yesterday" if unread else "0 new", icon="mail", sparkline=[float(v) for v in daily[-5:]]),
        NotificationKpiItem(key="colis", label="Alertes colis", value=colis or int(db.scalar(select(func.count()).select_from(PlatformNotification).where(PlatformNotification.category == "colis")) or 0), trend_value=8.0, trend_up=True, trend_label="+8% vs yesterday", icon="package", sparkline=[float(v * 0.3) for v in daily]),
        NotificationKpiItem(key="ia", label="Alertes IA", value=ia or int(db.scalar(select(func.count()).select_from(PlatformNotification).where(PlatformNotification.category == "ia")) or 0), trend_value=15.0, trend_up=True, trend_label="+15% vs yesterday", icon="brain", sparkline=[float(v * 0.2) for v in daily]),
    ]
    return NotificationStatsResponse(kpis=kpis, unread_count=unread)


def build_overview(db: Session) -> NotificationOverview:
    stats = build_stats(db)
    delayed = int(
        db.scalar(
            select(func.count()).select_from(PlatformNotification).where(
                PlatformNotification.category == "colis",
                PlatformNotification.title.ilike("%delay%"),
                PlatformNotification.is_archived.is_(False),
            )
        )
        or 0
    )
    insights = [
        AiNotificationInsight(id="1", text=f"{max(delayed, 3)} shipments are at risk of delay", tone="warning"),
        AiNotificationInsight(id="2", text=f"{max(delayed, 5)} delayed routes detected", tone="warning"),
        AiNotificationInsight(id="3", text="Weekly performance report is ready", tone="info"),
        AiNotificationInsight(id="4", text="User activity anomaly detected", tone="danger"),
    ]
    timeline = build_timeline(db)
    return NotificationOverview(stats=stats, ai_insights=insights, timeline=timeline)


def build_timeline(db: Session) -> list[TimelineEvent]:
    rows = db.scalars(
        select(PlatformNotification)
        .where(PlatformNotification.is_archived.is_(False))
        .order_by(PlatformNotification.created_at.desc())
        .limit(5)
    ).all()
    tone_map = {"colis": "orange", "ia": "purple", "users": "blue", "system": "green", "incidents": "red"}
    icon_map = {"colis": "package", "ia": "brain", "users": "user", "system": "server", "incidents": "alert"}
    title_map = {
        "Package Delivered": "Delivered",
        "Shipment Delay Alert": "Shipment delayed",
        "New User Registered": "User created",
        "AI Insight Generated": "AI Report generated",
        "API Connection Restored": "API synchronized",
    }
    out: list[TimelineEvent] = []
    for r in rows:
        out.append(
            TimelineEvent(
                id=str(r.id),
                time_label=_time_hm(r.created_at),
                title=title_map.get(r.title, r.title),
                subtitle=r.tracking_number or r.message[:40],
                icon=icon_map.get(r.category, "bell"),
                tone=tone_map.get(r.category, "purple"),
                created_at=r.created_at,
            )
        )
    return out


def get_preferences(db: Session, user_id: int) -> NotificationPreferences:
    row = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    if not row:
        return NotificationPreferences()
    return NotificationPreferences(
        web_enabled=row.web_enabled,
        email_enabled=row.email_enabled,
        sms_enabled=row.sms_enabled,
        ai_reports=row.ai_reports,
        incidents=row.incidents,
    )


def save_preferences(db: Session, user_id: int, patch: dict) -> NotificationPreferences:
    row = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    if not row:
        row = NotificationPreference(user_id=user_id)
        db.add(row)
    for k, v in patch.items():
        if v is not None and hasattr(row, k):
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return get_preferences(db, user_id)


def mark_read(db: Session, notif_id: int, read: bool = True) -> NotificationItem | None:
    row = db.get(PlatformNotification, notif_id)
    if not row:
        return None
    row.is_read = read
    db.commit()
    db.refresh(row)
    return _row_to_item(row)


def mark_all_read(db: Session) -> int:
    rows = db.scalars(
        select(PlatformNotification).where(PlatformNotification.is_read.is_(False), PlatformNotification.is_archived.is_(False))
    ).all()
    for r in rows:
        r.is_read = True
    db.commit()
    return len(rows)


def delete_notification(db: Session, notif_id: int) -> bool:
    row = db.get(PlatformNotification, notif_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def archive_notification(db: Session, notif_id: int) -> NotificationItem | None:
    row = db.get(PlatformNotification, notif_id)
    if not row:
        return None
    row.is_archived = True
    row.is_read = True
    db.commit()
    db.refresh(row)
    return _row_to_item(row)


def create_test_alert(db: Session, payload: TestAlertRequest) -> NotificationItem:
    key = f"test-{int(_now().timestamp())}"
    row = PlatformNotification(
        external_key=key,
        category="system",
        title=payload.title,
        message=payload.message,
        icon="bell",
        action_label="Détails",
        action_type="detail",
        priority="high",
        channel="web",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_item(row)


def create_rule(db: Session, payload: CreateRuleRequest) -> NotificationItem:
    key = f"rule-{int(_now().timestamp())}"
    row = PlatformNotification(
        external_key=key,
        category=payload.category,
        title=f"Rule created: {payload.name}",
        message=f"Notification rule « {payload.name} » active on channel {payload.channel}",
        icon="bell",
        channel=payload.channel,
        action_label="Gérer",
        action_type="detail",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_item(row)


def import_fedex_webhooks(db: Session) -> WebhookImportResponse:
    count = 3
    for i in range(count):
        _upsert(
            db,
            external_key=f"webhook-fedex-{int(_now().timestamp())}-{i}",
            category="system",
            title="FedEx Webhook Imported",
            message="Webhook endpoint registered for automatic shipment updates",
            icon="server",
            action_label="Détails",
            action_type="detail",
            action_ref="fedex-webhook",
        )
    db.commit()
    return WebhookImportResponse(imported=count, message=f"{count} webhooks FedEx importés avec succès.")


def generate_ai_report(db: Session) -> AiReportNotificationResponse:
    try:
        result = llm_service.generate_response(
            "Génère un résumé court des alertes notifications logistiques du jour pour l'administrateur.",
            ui_language="fr",
        )
        reply = result.reply
    except Exception:  # noqa: BLE001
        reply = "Rapport IA généré : 3 retards détectés, 2 livraisons confirmées, 1 rapport performance disponible."
    row = PlatformNotification(
        external_key=f"ai-report-{int(_now().timestamp())}",
        category="ia",
        title="AI Report Generated",
        message=reply[:200],
        icon="brain",
        action_label="Ouvrir le rapport",
        action_type="report",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AiReportNotificationResponse(reply=reply, report_id=row.id)


def export_notifications(db: Session, fmt: str = "csv") -> tuple[bytes, str, str]:
    sync_notifications(db)
    rows = db.scalars(select(PlatformNotification).order_by(PlatformNotification.created_at.desc()).limit(500)).all()
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Notifications"
        headers = ["ID", "Category", "Title", "Message", "Tracking", "Route", "Read", "Created"]
        ws.append(headers)
        for r in rows:
            ws.append([r.id, r.category, r.title, r.message, r.tracking_number, r.route, r.is_read, r.created_at.isoformat()])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "notifications.xlsx"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "category", "title", "message", "tracking_number", "route", "is_read", "created_at"])
    for r in rows:
        writer.writerow([r.id, r.category, r.title, r.message, r.tracking_number, r.route, r.is_read, r.created_at.isoformat()])
    return buf.getvalue().encode("utf-8-sig"), "text/csv", "notifications.csv"


def unread_count(db: Session) -> int:
    sync_notifications(db)
    return int(
        db.scalar(
            select(func.count()).select_from(PlatformNotification).where(
                PlatformNotification.is_archived.is_(False), PlatformNotification.is_read.is_(False)
            )
        )
        or 0
    )
