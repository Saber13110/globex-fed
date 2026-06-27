"""Données agrégées pour la page AI Assistant admin."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.report_run import ReportRun
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.tracking_request import TrackingRequest
from app.schemas.admin_ai import (
    AiAssistantOverview,
    AiAssistantKpi,
    AiCapabilityItem,
    AiConversationItem,
    AiDataSource,
    AiInsightItem,
    AiServiceStatus,
    AiSuggestionItem,
)
from app.services.command_center_service import build_command_center, _pct_change
from app.services.system_health_service import build_health, check_ai, check_database, check_fedex


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_hours(minutes: float) -> str:
    h = minutes / 60.0
    return f"{h:.1f}h"


def _build_kpis(db: Session) -> list[AiAssistantKpi]:
    start = _today_start()
    yesterday = start - timedelta(days=1)

    questions_today = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.sender == MessageSender.user.value, ChatMessage.created_at >= start)
        )
        or 0
    ) + int(
        db.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(ActivityLog.action == "admin.command_center_ai", ActivityLog.created_at >= start)
        )
        or 0
    )
    questions_yesterday = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.sender == MessageSender.user.value,
                ChatMessage.created_at >= yesterday,
                ChatMessage.created_at < start,
            )
        )
        or 0
    ) + int(
        db.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.action == "admin.command_center_ai",
                ActivityLog.created_at >= yesterday,
                ActivityLog.created_at < start,
            )
        )
        or 0
    )

    tasks_today = int(
        db.scalar(
            select(func.count())
            .select_from(ReportRun)
            .where(ReportRun.status == "completed", ReportRun.created_at >= start)
        )
        or 0
    ) + int(
        db.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(ActivityLog.action == "admin.command_center_ai", ActivityLog.created_at >= start)
        )
        or 0
    )
    tasks_yesterday = max(1, int(
        db.scalar(
            select(func.count())
            .select_from(ReportRun)
            .where(
                ReportRun.status == "completed",
                ReportRun.created_at >= yesterday,
                ReportRun.created_at < start,
            )
        )
        or 0
    ) + int(
        db.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.action == "admin.command_center_ai",
                ActivityLog.created_at >= yesterday,
                ActivityLog.created_at < start,
            )
        )
        or 0
    ))

    data_rows = int(db.scalar(select(func.count()).select_from(TrackingRequest)) or 0)
    data_msgs = int(db.scalar(select(func.count()).select_from(ChatMessage)) or 0)
    data_analyzed = data_rows + data_msgs
    data_prev = max(1, data_analyzed - questions_today)

    time_saved_min = tasks_today * 22 + questions_today * 3
    time_prev_min = max(1, tasks_yesterday * 22)

    q_pct, q_up = _pct_change(questions_today, questions_yesterday)
    t_pct, t_up = _pct_change(tasks_today, tasks_yesterday)
    d_pct, d_up = _pct_change(data_analyzed, data_prev)
    ts_pct, ts_up = _pct_change(int(time_saved_min), int(time_prev_min))

    return [
        AiAssistantKpi(
            key="questions",
            label="Questions Today",
            value=str(questions_today),
            trend_percent=q_pct,
            trend_up=q_up,
            icon="message",
        ),
        AiAssistantKpi(
            key="tasks",
            label="Tasks Completed",
            value=str(tasks_today),
            trend_percent=t_pct,
            trend_up=t_up,
            icon="check",
        ),
        AiAssistantKpi(
            key="data",
            label="Data Analyzed",
            value=_fmt_count(data_analyzed),
            trend_percent=d_pct,
            trend_up=d_up,
            icon="database",
        ),
        AiAssistantKpi(
            key="time",
            label="Time Saved",
            value=_fmt_hours(time_saved_min),
            trend_percent=ts_pct,
            trend_up=ts_up,
            icon="clock",
        ),
    ]


def _build_insights(db: Session) -> list[AiInsightItem]:
    cc = build_command_center(db)
    open_incidents = cc.open_incidents
    delayed = sum(1 for s in cc.live_shipments if s.status_key == "delayed")
    delivered = sum(1 for s in cc.live_shipments if s.status_key == "delivered")
    total_ship = max(len(cc.live_shipments), 1)
    perf_pct = round((delivered / total_ship) * 100)

    insights: list[AiInsightItem] = []
    if delayed >= 3:
        insights.append(
            AiInsightItem(
                id="delay",
                title="Delay Risk",
                description=f"High risk of delays on {delayed} active routes",
                tone="high",
                badge="High",
                icon="alert",
            )
        )
    else:
        insights.append(
            AiInsightItem(
                id="delay",
                title="Delay Risk",
                description="No critical delay clusters detected",
                tone="good",
                badge="Low",
                icon="alert",
            )
        )

    kpi_delivery = next((k for k in cc.kpis if "livraison" in k.title.lower() or "delivery" in k.title.lower()), None)
    trend_up = kpi_delivery.trend_up if kpi_delivery else True
    trend_val = kpi_delivery.trend_percent if kpi_delivery else 12.0
    insights.append(
        AiInsightItem(
            id="performance",
            title="Performance",
            description=f"Delivery performance at {perf_pct}% ({'+' if trend_up else '-'}{trend_val}% trend)",
            tone="good" if trend_up else "medium",
            badge="Good" if trend_up else "Watch",
            icon="chart",
        )
    )

    insights.append(
        AiInsightItem(
            id="exceptions",
            title="Exceptions",
            description=f"{open_incidents} exceptions need attention",
            tone="medium" if open_incidents else "good",
            badge="Medium" if open_incidents else "Clear",
            icon="exception",
        )
    )

    month = datetime.now(timezone.utc).month
    peak = month in (11, 12, 1)
    insights.append(
        AiInsightItem(
            id="trend",
            title="Trend",
            description="Peak season starting soon" if peak else "Operations volume stable this week",
            tone="info",
            badge="Info",
            icon="trend",
        )
    )
    return insights


def _build_system_status(db: Session) -> list[AiServiceStatus]:
    ai = check_ai()
    db_h = check_database(db)
    fedex = check_fedex()
    health = build_health(db)
    reports = next((s for s in health.services if s.key == "storage"), None)

    def _op(status: str) -> bool:
        return status in ("online", "operational")

    return [
        AiServiceStatus(
            key="ai_engine",
            name="AI Engine",
            status="Operational" if _op(ai.status) else ai.status.title(),
            operational=_op(ai.status),
        ),
        AiServiceStatus(
            key="data_processing",
            name="Data Processing",
            status="Operational" if _op(db_h.status) else db_h.status.title(),
            operational=_op(db_h.status),
        ),
        AiServiceStatus(
            key="analytics",
            name="Analytics",
            status="Operational" if _op(db_h.status) else "Degraded",
            operational=_op(db_h.status),
        ),
        AiServiceStatus(
            key="reports",
            name="Reports Service",
            status="Operational" if reports and _op(reports.status) else "Degraded",
            operational=bool(reports and _op(reports.status)),
        ),
        AiServiceStatus(
            key="fedex",
            name="FedEx Integration",
            status="Operational" if _op(fedex.status) else fedex.status.title(),
            operational=_op(fedex.status),
        ),
    ]


def _build_data_sources(db: Session) -> list[AiDataSource]:
    fedex = check_fedex()
    db_h = check_database(db)
    open_exc = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status == SupportTicketStatus.open)
        )
        or 0
    )
    users = int(db.scalar(select(func.count()).select_from(ChatSession)) or 0)

    return [
        AiDataSource(
            key="tracking",
            name="Tracking System",
            connected=fedex.status == "online",
            detail=fedex.detail or "FedEx API",
        ),
        AiDataSource(
            key="users",
            name="User Management",
            connected=db_h.status == "online",
            detail=f"{users} active sessions",
        ),
        AiDataSource(
            key="exceptions",
            name="Exceptions Database",
            connected=True,
            detail=f"{open_exc} open tickets",
        ),
        AiDataSource(
            key="external",
            name="External APIs",
            connected=fedex.status in ("online", "disabled"),
            detail="FedEx + SMTP" if fedex.status == "online" else fedex.detail,
        ),
    ]


def _build_suggestions(db: Session) -> list[AiSuggestionItem]:
    cc = build_command_center(db)
    suggestions: list[AiSuggestionItem] = []
    if cc.open_incidents:
        suggestions.append(
            AiSuggestionItem(
                id="exc-report",
                text="Generate monthly exception report",
                action="report",
            )
        )
    delayed = [s for s in cc.live_shipments if s.status_key == "delayed"]
    if delayed:
        suggestions.append(
            AiSuggestionItem(
                id="delayed",
                text="Identify top delayed shipments",
                action="delays",
            )
        )
    eu = [s for s in cc.live_shipments if "europe" in s.route.lower() or "paris" in s.route.lower() or "madrid" in s.route.lower()]
    if eu:
        suggestions.append(
            AiSuggestionItem(
                id="eu-routes",
                text="Analyze European routes",
                action="countries",
            )
        )
    if not suggestions:
        suggestions = [
            AiSuggestionItem(id="perf", text="Generate performance report", action="report"),
            AiSuggestionItem(id="activity", text="View user activity summary", action="activity"),
            AiSuggestionItem(id="delays", text="Analyze shipment delays", action="delays"),
        ]
    return suggestions[:4]


def _conversation_status(created_at: datetime, is_latest: bool) -> str:
    age = datetime.now(timezone.utc) - (created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc))
    if is_latest and age < timedelta(minutes=2):
        return "running"
    if age < timedelta(minutes=1):
        return "pending"
    return "completed"


def _build_recent_conversations(db: Session) -> list[AiConversationItem]:
    items: list[AiConversationItem] = []

    admin_logs = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.action == "admin.command_center_ai")
        .order_by(ActivityLog.created_at.desc())
        .limit(8)
    ).all()
    for i, row in enumerate(admin_logs):
        q = row.message.replace("Requête IA admin: ", "").strip()
        items.append(
            AiConversationItem(
                id=row.id,
                question=q[:180],
                created_at=row.created_at,
                status=_conversation_status(row.created_at, i == 0),
                source="admin",
            )
        )

    sessions = db.scalars(
        select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(6)
    ).all()
    for sess in sessions:
        first_user = db.scalar(
            select(ChatMessage)
            .where(ChatMessage.session_id == sess.id, ChatMessage.sender == MessageSender.user.value)
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        if not first_user:
            continue
        items.append(
            AiConversationItem(
                id=100000 + sess.id,
                question=(first_user.message_text or sess.title or "Conversation")[:180],
                created_at=first_user.created_at,
                status="completed",
                source="platform",
                session_id=sess.id,
            )
        )

    items.sort(key=lambda x: x.created_at, reverse=True)
    seen: set[str] = set()
    unique: list[AiConversationItem] = []
    for item in items:
        key = item.question[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:12]


def build_ai_assistant_overview(db: Session) -> AiAssistantOverview:
    return AiAssistantOverview(
        kpis=_build_kpis(db),
        insights=_build_insights(db),
        capabilities=[
            AiCapabilityItem(key="nlq", title="Natural Language Query", description="Ask in plain language", icon="chat"),
            AiCapabilityItem(key="predict", title="Predictive Analytics", description="Forecast delays & risks", icon="spark"),
            AiCapabilityItem(key="analysis", title="Data Analysis", description="Cross-platform insights", icon="chart"),
            AiCapabilityItem(key="reports", title="Automated Reports", description="Generate & export instantly", icon="file"),
        ],
        system_status=_build_system_status(db),
        data_sources=_build_data_sources(db),
        smart_suggestions=_build_suggestions(db),
        ask_examples=[
            "What are the top 5 delayed shipments today?",
            "Show delivery performance by country",
            "Generate a summary of exceptions this week",
            "Predict delays for tomorrow",
        ],
        recent_conversations=_build_recent_conversations(db),
        quick_commands=[
            "Analyze shipment delays",
            "Top exceptions today",
            "Generate performance report",
            "View user activity",
            "Compare countries",
            "Predict delivery issues",
        ],
    )
