"""Collecte déterministe des faits dashboard admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.command_center import (
    ActivityTimelineItem,
    CommandCenterPayload,
    LiveShipmentItem,
    RecentConversationItem,
    RecentUserItem,
)
from app.services.admin_client.dashboard.dashboard_tool import (
    DashboardSummaryError,
    fetch_command_center_and_summary,
)


@dataclass
class DashboardSnapshot:
    lang: str
    command_center: CommandCenterPayload
    summary: dict[str, Any] = field(default_factory=dict)
    delayed_shipments: list[LiveShipmentItem] = field(default_factory=list)
    new_users: list[RecentUserItem] = field(default_factory=list)
    suspicious_logs: list[ActivityTimelineItem] = field(default_factory=list)
    users_by_role: dict[str, int] = field(default_factory=dict)
    users_by_status: dict[str, int] = field(default_factory=dict)
    shipment_status_counts: dict[str, int] = field(default_factory=dict)
    activity_level_counts: dict[str, int] = field(default_factory=dict)
    anomaly_flags: list[str] = field(default_factory=list)
    period: str = "today"


def collect_dashboard_snapshot(
    db: Session,
    *,
    lang: str = "fr",
    period: str = "today",
    role_filter: str = "all",
    status_filter: str = "all",
) -> DashboardSnapshot:
    """Agrège get_dashboard_summary + enrichissements snapshot."""
    try:
        cc, summary = fetch_command_center_and_summary(
            db, lang=lang, period=period, role_filter=role_filter
        )
    except DashboardSummaryError as exc:
        raise DashboardSummaryError(str(exc)) from exc
    delayed = [s for s in cc.live_shipments if s.status_key == "delayed"]

    recent_users = [
        u
        for u in cc.recent_users
        if any(
            nu.get("email") == u.email
            for nu in (summary.get("new_users") or [])
        )
    ]
    if not recent_users and summary.get("new_users"):
        recent_users = [
            RecentUserItem(
                id=i + 1,
                full_name=str(u.get("full_name") or ""),
                email=str(u.get("email") or ""),
                role=str(u.get("role") or "client"),
                created_at=datetime.now(timezone.utc),
            )
            for i, u in enumerate(summary["new_users"])
        ]

    suspicious = [
        a
        for a in cc.activity_timeline
        if (a.level or "").upper() in ("WARNING", "ERROR", "CRITICAL")
    ]

    status_counts: dict[str, int] = {}
    for s in cc.live_shipments:
        key = s.status_key or "in_transit"
        status_counts[key] = status_counts.get(key, 0) + 1

    level_counts: dict[str, int] = {}
    for a in cc.activity_timeline:
        key = (a.level or "INFO").upper()
        level_counts[key] = level_counts.get(key, 0) + 1

    role_rows = db.execute(
        select(User.role, func.count()).group_by(User.role)
    ).all()
    users_by_role = {str(r[0]): int(r[1]) for r in role_rows}

    status_rows = db.execute(
        select(User.status, func.count()).group_by(User.status)
    ).all()
    users_by_status = {str(s[0]): int(s[1]) for s in status_rows}

    if role_filter != "all":
        recent_users = [u for u in recent_users if u.role == role_filter]

    snap = DashboardSnapshot(
        lang=lang,
        command_center=cc,
        summary=summary,
        delayed_shipments=delayed,
        new_users=recent_users,
        suspicious_logs=suspicious,
        users_by_role=users_by_role,
        users_by_status=users_by_status,
        shipment_status_counts=status_counts,
        activity_level_counts=level_counts,
        period=period,
    )
    from app.services.admin_client.dashboard.dashboard_anomalies import detect_anomalies

    snap.anomaly_flags = summary.get("anomalies") or detect_anomalies(snap)
    return snap


def compact_dashboard_facts(snapshot: DashboardSnapshot) -> dict[str, Any]:
    """Faits compacts pour synthèse LLM optionnelle."""
    if snapshot.summary:
        s = snapshot.summary
        return {
            k: s.get(k)
            for k in (
                "shipments_today",
                "delivered_today",
                "in_transit",
                "delayed_shipments",
                "active_users",
                "total_users",
                "open_incidents",
                "fedex_requests_today",
                "fedex_error_rate",
                "anomalies",
                "period",
            )
        }
    cc = snapshot.command_center
    return {
        "open_incidents": cc.open_incidents,
        "total_users": cc.total_users,
        "delayed_count": len(snapshot.delayed_shipments),
        "fedex_requests_today": cc.fedex_metrics.requests_today,
        "fedex_error_rate": cc.fedex_metrics.error_rate,
        "anomalies": snapshot.anomaly_flags,
        "period": snapshot.period,
    }
