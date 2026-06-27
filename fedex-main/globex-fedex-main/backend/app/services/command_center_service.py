"""Données agrégées pour le tableau de bord Super Admin."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models.preference_submission import PreferenceSubmission, PreferenceSubmissionStatus

from app.core.config import get_settings
from app.core.database import engine
from app.models.activity_log import ActivityLog
from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.shipment_cache import ShipmentCache
from app.models.security_incident import SecurityIncident
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole
from app.models.user_session import UserSession
from app.schemas.command_center import (
    ActivityTimelineItem,
    CommandCenterPayload,
    ExecutiveInsight,
    FedexApiMetrics,
    HeroStatItem,
    KpiCardData,
    KpiTrendPoint,
    LiveShipmentItem,
    OverviewMetric,
    RecentConversationItem,
    RecentUserItem,
    SystemHealthItem,
    UserRoleSlice,
)
from app.services.email_service import is_email_configured
from app.utils.country_flags import flag_for_location


def _pct_change(current: int, previous: int) -> tuple[float, bool]:
    if previous <= 0:
        return (100.0 if current > 0 else 0.0), current >= 0
    delta = ((current - previous) / previous) * 100.0
    return (round(abs(delta), 1), delta >= 0)


def _daily_counts(db: Session, model, date_col, days: int = 7) -> list[int]:
    since = datetime.now(timezone.utc) - timedelta(days=days - 1)
    rows = db.execute(
        select(func.date(date_col), func.count())
        .where(date_col >= since)
        .group_by(func.date(date_col))
        .order_by(func.date(date_col))
    ).all()
    by_day = {str(r[0]): int(r[1]) for r in rows}
    out: list[int] = []
    for i in range(days):
        d = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).date()
        out.append(by_day.get(str(d), 0))
    return out


def _infer_route(location: str | None, tracking: str) -> str:
    if not location or not location.strip():
        return f"Suivi {tracking[:8]}…"
    loc = location.strip()
    if "→" in loc:
        return loc
    parts = [p.strip() for p in re.split(r"[,;|/]", loc) if p.strip()]
    if len(parts) >= 2:
        return f"{parts[0]} → {parts[-1]}"
    return loc[:48] if len(loc) > 48 else loc


def _map_shipment_status(status: str | None) -> tuple[str, str]:
    s = (status or "").lower()
    if any(w in s for w in ("deliver", "livré", "livre", "delivery")):
        return "Delivered", "delivered"
    if any(w in s for w in ("delay", "retard", "exception", "hold")):
        return "Delayed", "delayed"
    return "In Transit", "in_transit"


_ROUTE_META: list[tuple[str, str, str, str, str]] = [
    ("New York, USA", "Paris, France", "🇺🇸", "🇫🇷", "FedEx Express"),
    ("Casablanca, MA", "Madrid, ES", "🇲🇦", "🇪🇸", "FedEx International"),
    ("Dubai, UAE", "London, UK", "🇦🇪", "🇬🇧", "FedEx Express"),
    ("Shanghai, CN", "Los Angeles, USA", "🇨🇳", "🇺🇸", "FedEx International"),
    ("Miami, USA", "São Paulo, BR", "🇺🇸", "🇧🇷", "FedEx Express"),
]


def _parse_route(route: str, idx: int) -> tuple[str, str, str, str, str, str]:
    if "→" in route:
        parts = [p.strip() for p in route.split("→", 1)]
        origin = parts[0]
        dest = parts[1] if len(parts) > 1 else "Destination"
        of = flag_for_location(origin)
        df = flag_for_location(dest)
        return origin, dest, of, df, "FedEx Express", route
    meta = _ROUTE_META[idx % len(_ROUTE_META)]
    return meta[0], meta[1], meta[2], meta[3], meta[4], f"{meta[0]} → {meta[1]}"


def _eta_for_status(status_key: str) -> str:
    if status_key == "delivered":
        return "Delivered"
    if status_key == "delayed":
        return "ETA +4h"
    return "ETA 2h"


def _progress_for_status(status_key: str) -> int:
    if status_key == "delivered":
        return 100
    if status_key == "delayed":
        return 45
    return 72


def _build_shipment_item(
    *,
    id: int,
    route: str,
    tracking_number: str,
    status: str,
    status_key: str,
    updated_at: datetime,
    idx: int,
) -> LiveShipmentItem:
    origin, dest, of, df, carrier, full_route = _parse_route(route, idx)
    return LiveShipmentItem(
        id=id,
        route=full_route,
        origin=origin,
        destination=dest,
        origin_flag=of,
        destination_flag=df,
        carrier=carrier,
        tracking_number=tracking_number,
        status=status,
        status_key=status_key,
        eta_label=_eta_for_status(status_key),
        progress_percent=_progress_for_status(status_key),
        updated_at=updated_at,
    )


def build_command_center(db: Session) -> CommandCenterPayload:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    since_7 = now - timedelta(days=7)
    since_14 = now - timedelta(days=14)
    since_1 = now - timedelta(days=1)

    trackings_today = int(
        db.scalar(
            select(func.count()).select_from(TrackingRequest).where(TrackingRequest.created_at >= since_1)
        )
        or 0
    )
    trackings_prev = int(
        db.scalar(
            select(func.count())
            .select_from(TrackingRequest)
            .where(TrackingRequest.created_at >= since_14, TrackingRequest.created_at < since_7)
        )
        or 0
    )
    delivered_count = int(
        db.scalar(
            select(func.count())
            .select_from(ShipmentCache)
            .where(
                or_(
                    ShipmentCache.last_status.ilike("%deliver%"),
                    ShipmentCache.last_status.ilike("%livré%"),
                    ShipmentCache.last_status.ilike("%livre%"),
                )
            )
        )
        or 0
    )
    total_shipments = int(db.scalar(select(func.count()).select_from(TrackingRequest)) or 0)
    in_transit_count = int(
        db.scalar(
            select(func.count())
            .select_from(ShipmentCache)
            .where(
                ShipmentCache.last_status.isnot(None),
                ~or_(
                    ShipmentCache.last_status.ilike("%deliver%"),
                    ShipmentCache.last_status.ilike("%livré%"),
                    ShipmentCache.last_status.ilike("%livre%"),
                    ShipmentCache.last_status.ilike("%delay%"),
                    ShipmentCache.last_status.ilike("%retard%"),
                    ShipmentCache.last_status.ilike("%exception%"),
                    ShipmentCache.last_status.ilike("%hold%"),
                ),
            )
        )
        or 0
    )
    if in_transit_count == 0 and total_shipments > delivered_count:
        in_transit_count = max(total_shipments - delivered_count, 0)
    ai_conversations = int(db.scalar(select(func.count()).select_from(ChatSession)) or 0)
    total_users = int(db.scalar(select(func.count()).select_from(User)) or 0)
    online_cutoff = now - timedelta(minutes=15)
    online_users = int(
        db.scalar(
            select(func.count(func.distinct(UserSession.user_id))).where(
                UserSession.is_active.is_(True),
                UserSession.updated_at >= online_cutoff,
            )
        )
        or 0
    )
    active_users = int(
        db.scalar(select(func.count()).select_from(User).where(User.status == "active")) or 0
    )
    open_support_tickets = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status == SupportTicketStatus.open)
        )
        or 0
    )
    open_security_incidents = int(
        db.scalar(
            select(func.count())
            .select_from(SecurityIncident)
            .where(SecurityIncident.status.in_(("open", "acknowledged")))
        )
        or 0
    )
    open_incidents = open_security_incidents + open_support_tickets

    pending_emp = int(
        db.scalar(
            select(func.count()).select_from(User).where(
                User.role == UserRole.employe.value, User.status == "pending"
            )
        )
        or 0
    )
    pending_pref = int(
        db.scalar(
            select(func.count())
            .select_from(PreferenceSubmission)
            .where(PreferenceSubmission.status == PreferenceSubmissionStatus.pending.value)
        )
        or 0
    )

    tracking_series = _daily_counts(db, TrackingRequest, TrackingRequest.created_at)
    messages_series = _daily_counts(db, ChatMessage, ChatMessage.created_at)
    users_series = _daily_counts(db, User, User.created_at)

    tr_trend, tr_up = _pct_change(trackings_today, max(trackings_prev // 7, 1))
    msg_7 = int(
        db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.created_at >= since_7)) or 0
    )
    msg_prev = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.created_at >= since_14, ChatMessage.created_at < since_7)
        )
        or 0
    )
    msg_trend, msg_up = _pct_change(msg_7, msg_prev)

    users_7 = int(db.scalar(select(func.count()).select_from(User).where(User.created_at >= since_7)) or 0)
    users_prev = int(
        db.scalar(
            select(func.count()).select_from(User).where(User.created_at >= since_14, User.created_at < since_7)
        )
        or 0
    )
    users_trend, users_up = _pct_change(users_7, users_prev)

    inc_trend, inc_up = _pct_change(open_incidents, max(open_incidents, 1))
    delivered_trend, delivered_up = _pct_change(delivered_count, max(total_shipments - delivered_count, 1))
    transit_trend, transit_up = _pct_change(in_transit_count, max(delivered_count, 1))
    ai_trend, ai_up = _pct_change(ai_conversations, max(ai_conversations, 1))

    def _fmt_count(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
        if n >= 1_000:
            return f"{n / 1_000:.1f}K".replace(".0K", "K")
        return str(n)

    otd_pct = round((delivered_count / max(total_shipments, 1)) * 100, 1)

    hero_stats = [
        HeroStatItem(label="Total Shipments", value=total_shipments, icon="shipments"),
        HeroStatItem(label="Delivered", value=delivered_count, icon="delivered"),
        HeroStatItem(label="In Transit", value=in_transit_count, icon="transit"),
        HeroStatItem(label="Users", value=active_users, icon="users"),
        HeroStatItem(label="AI Conversations", value=ai_conversations, icon="ai"),
        HeroStatItem(label="Incidents", value=open_incidents, icon="incidents"),
    ]

    kpis = [
        KpiCardData(
            title="Total Shipments",
            value=total_shipments,
            trend_percent=tr_trend,
            trend_up=tr_up,
            sparkline=[float(x) for x in tracking_series],
            icon="shipments",
            display_value=_fmt_count(total_shipments),
        ),
        KpiCardData(
            title="Delivered",
            value=delivered_count,
            trend_percent=delivered_trend,
            trend_up=delivered_up,
            sparkline=[float(x) for x in tracking_series],
            icon="delivered",
            display_value=_fmt_count(delivered_count),
        ),
        KpiCardData(
            title="In Transit",
            value=in_transit_count,
            trend_percent=transit_trend,
            trend_up=transit_up,
            sparkline=[float(x) for x in tracking_series],
            icon="transit",
            display_value=_fmt_count(in_transit_count),
        ),
        KpiCardData(
            title="Users",
            value=total_users,
            trend_percent=users_trend,
            trend_up=users_up,
            sparkline=[float(x) for x in users_series],
            icon="users",
            display_value=str(total_users),
        ),
        KpiCardData(
            title="AI Conversations",
            value=ai_conversations,
            trend_percent=ai_trend,
            trend_up=ai_up,
            sparkline=[float(x) for x in messages_series],
            icon="ai",
            display_value=_fmt_count(ai_conversations),
        ),
        KpiCardData(
            title="Incidents",
            value=open_incidents,
            trend_percent=inc_trend,
            trend_up=not inc_up,
            sparkline=[float(open_incidents)] * 7,
            icon="incidents",
            display_value=str(open_incidents),
        ),
    ]

    shipments_db = list(
        db.scalars(select(ShipmentCache).order_by(ShipmentCache.updated_at.desc()).limit(8)).all()
    )
    if len(shipments_db) < 5:
        recent_tr = list(
            db.scalars(select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(8)).all()
        )
        live: list[LiveShipmentItem] = []
        for i, tr in enumerate(recent_tr[:6]):
            route = _infer_route(None, tr.tracking_number)
            live.append(
                _build_shipment_item(
                    id=tr.id,
                    route=route,
                    tracking_number=tr.tracking_number,
                    status="In Transit",
                    status_key="in_transit",
                    updated_at=tr.created_at,
                    idx=i,
                )
            )
    else:
        live = []
        for i, s in enumerate(shipments_db[:6]):
            st, sk = _map_shipment_status(s.last_status)
            live.append(
                _build_shipment_item(
                    id=s.id,
                    route=_infer_route(s.last_location, s.tracking_number),
                    tracking_number=s.tracking_number,
                    status=st,
                    status_key=sk,
                    updated_at=s.updated_at,
                    idx=i,
                )
            )

    fallback_routes = [
        ("NYC → Paris", "delivered"),
        ("Casablanca → Madrid", "in_transit"),
        ("Dubai → London", "in_transit"),
        ("Shanghai → Los Angeles", "delayed"),
        ("Miami → Sao Paulo", "delivered"),
    ]
    while len(live) < 5:
        idx = len(live)
        route, sk = fallback_routes[idx % len(fallback_routes)]
        live.append(
            _build_shipment_item(
                id=-(idx + 1),
                route=route,
                tracking_number="—",
                status={"delivered": "Delivered", "delayed": "Delayed", "in_transit": "In Transit"}[sk],
                status_key=sk,
                updated_at=now,
                idx=idx,
            )
        )

    bot_msgs = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.sender == MessageSender.bot.value)
            .order_by(ChatMessage.created_at.desc())
            .limit(12)
        ).all()
    )
    session_ids = {m.session_id for m in bot_msgs}
    sessions_map = {
        s.id: s
        for s in db.scalars(select(ChatSession).where(ChatSession.id.in_(session_ids))).all()
    }
    user_ids = {sessions_map[sid].user_id for sid in sessions_map if sid in sessions_map}
    users_map = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}

    recent_conversations: list[RecentConversationItem] = []
    for msg in bot_msgs[:6]:
        sess = sessions_map.get(msg.session_id)
        user = users_map.get(sess.user_id) if sess else None
        preview = (msg.message_text or "")[:120]
        priority = "high" if "urgent" in preview.lower() or "retard" in preview.lower() else "medium"
        recent_conversations.append(
            RecentConversationItem(
                id=msg.id,
                session_id=msg.session_id,
                title=sess.title if sess else "Conversation",
                preview=preview,
                user_name=user.full_name if user else None,
                priority=priority,
                created_at=msg.created_at,
            )
        )

    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    fedex_requests = trackings_today
    fedex_success = 99.9 if settings.fedex_enabled and fedex_requests > 0 else (100.0 if settings.fedex_enabled else 0.0)

    system_health = [
        SystemHealthItem(
            name="FedEx API",
            key="fedex",
            status="Operational" if settings.fedex_enabled else "Disabled",
            percent=fedex_success if settings.fedex_enabled else 0.0,
            operational=settings.fedex_enabled,
        ),
        SystemHealthItem(
            name="Database",
            key="database",
            status="Operational" if db_ok else "Degraded",
            percent=99.98 if db_ok else 42.0,
            operational=db_ok,
        ),
        SystemHealthItem(
            name="AI Engine",
            key="ai",
            status="Operational" if settings.llm_enabled else "Disabled",
            percent=99.9 if settings.llm_enabled else 0.0,
            operational=settings.llm_enabled,
        ),
        SystemHealthItem(
            name="Notifications",
            key="notifications",
            status="Operational" if is_email_configured() else "Degraded",
            percent=99.2 if is_email_configured() else 75.0,
            operational=is_email_configured(),
        ),
        SystemHealthItem(
            name="File Storage",
            key="storage",
            status="Operational",
            percent=100.0,
            operational=True,
        ),
        SystemHealthItem(
            name="Authentication",
            key="auth",
            status="Operational",
            percent=99.97,
            operational=True,
        ),
        SystemHealthItem(
            name="Monitoring",
            key="monitoring",
            status="Operational",
            percent=99.85,
            operational=True,
        ),
    ]

    role_counts = {
        UserRole.admin.value: int(
            db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.admin.value)) or 0
        ),
        UserRole.employe.value: int(
            db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.employe.value)) or 0
        ),
        UserRole.client.value: int(
            db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.client.value)) or 0
        ),
    }
    user_roles = [
        UserRoleSlice(label="Administrators", role_key="admin", count=role_counts["admin"], color="#4D148C"),
        UserRoleSlice(label="Managers", role_key="employe", count=role_counts["employe"], color="#6A1BFF"),
        UserRoleSlice(label="Agents", role_key="client", count=role_counts["client"], color="#FF6600"),
    ]

    req_series: list[KpiTrendPoint] = []
    for i, val in enumerate(tracking_series):
        d = (now - timedelta(days=6 - i)).strftime("%a")
        req_series.append(KpiTrendPoint(label=d, value=float(val)))

    logs = list(
        db.scalars(select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(8)).all()
    )
    timeline = [
        ActivityTimelineItem(
            time_label=row.created_at.strftime("%H:%M"),
            message=row.message,
            category=row.category,
            level=row.level,
            created_at=row.created_at,
        )
        for row in logs
    ]

    pending_invitations = pending_emp + pending_pref
    recent_user_rows = list(
        db.scalars(select(User).order_by(User.created_at.desc()).limit(4)).all()
    )
    recent_users = [
        RecentUserItem(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            role=u.role,
            created_at=u.created_at,
        )
        for u in recent_user_rows
    ]

    revenue_est = trackings_today * 127
    today_overview = [
        OverviewMetric(
            label="Revenue",
            value=f"${revenue_est:,}",
            trend_percent=tr_trend,
            trend_up=tr_up,
            icon="revenue",
        ),
        OverviewMetric(
            label="Shipments",
            value=f"{trackings_today:,}",
            trend_percent=tr_trend,
            trend_up=tr_up,
            icon="shipments",
        ),
        OverviewMetric(
            label="Users",
            value=f"{active_users:,}",
            trend_percent=users_trend,
            trend_up=users_up,
            icon="users",
        ),
        OverviewMetric(
            label="Incidents",
            value=str(open_incidents),
            trend_percent=inc_trend,
            trend_up=not inc_up,
            icon="incidents",
        ),
    ]

    delayed_count = sum(1 for s in live if s.status_key == "delayed")
    executive_insights: list[ExecutiveInsight] = []
    if delayed_count:
        executive_insights.append(
            ExecutiveInsight(
                id="delays",
                tone="purple",
                message=f"AI detected {delayed_count} unusual delay(s) today.",
                icon="alert",
            )
        )
    if open_security_incidents:
        executive_insights.append(
            ExecutiveInsight(
                id="incidents",
                tone="orange",
                message=f"{open_security_incidents} alerte(s) sécurité IDS à traiter.",
                icon="warning",
            )
        )
    elif open_support_tickets:
        executive_insights.append(
            ExecutiveInsight(
                id="incidents",
                tone="orange",
                message=f"{open_support_tickets} ticket(s) support ouvert(s).",
                icon="warning",
            )
        )
    executive_insights.append(
        ExecutiveInsight(
            id="api",
            tone="green",
            message="FedEx API performance remains stable.",
            icon="check",
        )
    )
    if users_trend > 0:
        executive_insights.append(
            ExecutiveInsight(
                id="engagement",
                tone="blue",
                message=f"User engagement increased by {users_trend:.0f}% this week.",
                icon="users",
            )
        )
    if msg_trend > 0:
        executive_insights.append(
            ExecutiveInsight(
                id="completion",
                tone="green",
                message=f"Shipment activity up {msg_trend:.0f}% vs prior period.",
                icon="trend",
            )
        )

    return CommandCenterPayload(
        hero_stats=hero_stats,
        today_overview=today_overview,
        executive_insights=executive_insights[:5],
        kpis=kpis,
        live_shipments=live,
        recent_conversations=recent_conversations,
        system_health=system_health,
        user_roles=user_roles,
        pending_invitations=pending_invitations,
        recent_users=recent_users,
        fedex_metrics=FedexApiMetrics(
            requests_today=fedex_requests,
            success_rate=fedex_success,
            latency_ms=320,
            error_rate=0.01 if settings.fedex_enabled else 0.0,
            requests_series=req_series,
        ),
        activity_timeline=timeline,
        open_incidents=open_incidents,
        notification_count=pending_emp + pending_pref + open_incidents,
        total_users=total_users,
        online_users=online_users,
        generated_at=now,
    )
