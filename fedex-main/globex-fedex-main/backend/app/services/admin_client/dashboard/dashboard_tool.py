"""Outil get_dashboard_summary — schéma canonique admin dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.command_center import CommandCenterPayload
from app.services.command_center_service import build_command_center


class DashboardSummaryError(Exception):
    """Échec collecte dashboard."""


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now - timedelta(days=30)
    return now - timedelta(days=7)


def _parse_metric_value(raw: str | int | float | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(str(raw).replace(",", "").replace(" ", "").strip())
    except ValueError:
        return None


def _overview_int(cc: CommandCenterPayload, label: str) -> int | None:
    for m in cc.today_overview:
        if m.label.lower() == label.lower():
            return _parse_metric_value(m.value)
    return None


def _hero_int(cc: CommandCenterPayload, *needles: str) -> int | None:
    for h in cc.hero_stats:
        lab = h.label.lower()
        if any(n.lower() in lab for n in needles):
            return int(h.value)
    return None


def _blocked_count(cc: CommandCenterPayload) -> int:
    blocked = 0
    for s in cc.live_shipments:
        key = (s.status_key or "").lower()
        status = (s.status or "").lower()
        if key in ("delayed", "blocked", "exception", "hold") or any(
            w in status for w in ("hold", "exception", "blocked", "retard")
        ):
            if key != "delayed":
                blocked += 1
    return blocked


def _build_canonical_from_cc(
    cc: CommandCenterPayload,
    *,
    lang: str,
    period: str,
    users_by_role: dict[str, int] | None = None,
    users_by_status: dict[str, int] | None = None,
    new_users: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    delayed_list = [s for s in cc.live_shipments if s.status_key == "delayed"]
    delayed_count = len(delayed_list)

    active_users = _overview_int(cc, "Users") or _hero_int(cc, "Users") or cc.total_users
    shipments_today = _overview_int(cc, "Shipments") or _hero_int(cc, "Total Shipments") or 0
    delivered_today = _hero_int(cc, "Delivered") or 0
    in_transit = _hero_int(cc, "In Transit") or max(
        len(cc.live_shipments) - delayed_count - delivered_today, 0
    )

    recent_activity = [
        {
            "time_label": a.time_label,
            "message": a.message,
            "level": a.level,
            "category": a.category,
        }
        for a in cc.activity_timeline
    ]

    system_health = [
        {
            "name": h.name,
            "key": h.key,
            "percent": h.percent,
            "operational": h.operational,
            "status": h.status,
        }
        for h in cc.system_health
    ]

    recent_conversations = [
        {
            "id": c.id,
            "title": c.title,
            "preview": c.preview,
            "user_name": c.user_name,
            "priority": c.priority,
        }
        for c in cc.recent_conversations
    ]

    delayed_shipments_detail = [
        {
            "tracking_number": s.tracking_number,
            "status": s.status,
            "route": s.route,
            "eta_label": s.eta_label,
        }
        for s in delayed_list
    ]

    return {
        "lang": lang,
        "period": period,
        "shipments_today": shipments_today,
        "delivered_today": delivered_today,
        "in_transit": in_transit,
        "delayed_shipments": delayed_count,
        "blocked_shipments": _blocked_count(cc),
        "active_users": active_users,
        "online_users": cc.online_users,
        "total_users": cc.total_users,
        "open_incidents": cc.open_incidents,
        "open_security_incidents": None,
        "open_support_tickets": None,
        "fedex_requests_today": cc.fedex_metrics.requests_today,
        "fedex_error_rate": cc.fedex_metrics.error_rate,
        "fedex_success_rate": cc.fedex_metrics.success_rate,
        "pending_invitations": cc.pending_invitations,
        "system_health": system_health,
        "recent_activity": recent_activity,
        "recent_conversations": recent_conversations,
        "delayed_shipments_detail": delayed_shipments_detail,
        "users_by_role": users_by_role or {},
        "users_by_status": users_by_status or {},
        "new_users": new_users or [],
        "generated_at": (
            cc.generated_at.isoformat() if cc.generated_at else datetime.now(timezone.utc).isoformat()
        ),
    }


def fetch_command_center_and_summary(
    db: Session,
    *,
    lang: str = "fr",
    period: str = "today",
    role_filter: str = "all",
) -> tuple[CommandCenterPayload, dict[str, Any]]:
    """Une seule collecte build_command_center → schéma canonique."""
    try:
        cc = build_command_center(db)
    except Exception as exc:
        raise DashboardSummaryError(str(exc)) from exc

    period_start = _period_start(period)

    new_users_raw = [
        u
        for u in cc.recent_users
        if u.created_at and _as_utc(u.created_at) >= period_start
    ]
    if role_filter != "all":
        new_users_raw = [u for u in new_users_raw if u.role == role_filter]

    new_users = [
        {"full_name": u.full_name, "email": u.email, "role": u.role}
        for u in new_users_raw
    ]

    role_rows = db.execute(select(User.role, func.count()).group_by(User.role)).all()
    users_by_role = {str(r[0]): int(r[1]) for r in role_rows}
    status_rows = db.execute(select(User.status, func.count()).group_by(User.status)).all()
    users_by_status = {str(s[0]): int(s[1]) for s in status_rows}

    summary = _build_canonical_from_cc(
        cc,
        lang=lang,
        period=period,
        users_by_role=users_by_role,
        users_by_status=users_by_status,
        new_users=new_users,
    )

    from app.services.admin_client.dashboard.dashboard_anomalies import detect_dashboard_anomalies

    anomalies, data_quality = detect_dashboard_anomalies(summary)
    summary["anomalies"] = anomalies
    summary["data_quality"] = data_quality
    return cc, summary


def get_dashboard_summary(
    db: Session,
    *,
    lang: str = "fr",
    period: str = "today",
    role_filter: str = "all",
) -> dict[str, Any]:
    """Collecte normalisée depuis build_command_center — source unique dashboard admin."""
    _, summary = fetch_command_center_and_summary(
        db, lang=lang, period=period, role_filter=role_filter
    )
    return summary
