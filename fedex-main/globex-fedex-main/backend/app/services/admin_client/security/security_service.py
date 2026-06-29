"""Façade métier Security IDS admin — délègue security_ids_service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.security_incident import SecurityIncident
from app.services.admin_client.security.security_types import SecurityToolError
from app.services.security_ids_service import (
    INCIDENT_ACK,
    INCIDENT_FALSE_POSITIVE,
    INCIDENT_OPEN,
    INCIDENT_RESOLVED,
    incident_to_read,
    list_incidents,
    run_ai_ids_scan,
    run_rule_scan,
)

_ACTIVE_STATUSES = (INCIDENT_OPEN, INCIDENT_ACK)

_STATUS_ALIASES: dict[str, str | tuple[str, ...]] = {
    "open": _ACTIVE_STATUSES,
    "ouverts": _ACTIVE_STATUSES,
    "active": _ACTIVE_STATUSES,
    "actifs": _ACTIVE_STATUSES,
    "resolved": INCIDENT_RESOLVED,
    "resolus": INCIDENT_RESOLVED,
    "résolus": INCIDENT_RESOLVED,
    "fermes": INCIDENT_RESOLVED,
    "fermés": INCIDENT_RESOLVED,
    "closed": INCIDENT_RESOLVED,
    "false_positive": INCIDENT_FALSE_POSITIVE,
    "faux_positif": INCIDENT_FALSE_POSITIVE,
    "faux positif": INCIDENT_FALSE_POSITIVE,
    "fp": INCIDENT_FALSE_POSITIVE,
    "acknowledged": INCIDENT_ACK,
    "ack": INCIDENT_ACK,
    "all": "all",
    "tous": "all",
}


def _normalize_status_filter(raw: str | None) -> str | tuple[str, ...] | None:
    if not raw:
        return _ACTIVE_STATUSES
    key = (raw or "").strip().lower()
    return _STATUS_ALIASES.get(key, key)


def _open_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(SecurityIncident)
            .where(SecurityIncident.status.in_(_ACTIVE_STATUSES))
        )
        or 0
    )


def list_incidents_filtered(
    db: Session,
    *,
    status_filter: str | None = None,
    severity_filter: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, int]:
    limit = min(max(int(limit or 30), 1), 100)
    offset = max(int(offset or 0), 0)
    status = _normalize_status_filter(status_filter)

    if status == "all":
        rows, total, _ = list_incidents(db, status="all", limit=limit, offset=offset)
        return [incident_to_read(db, r) for r in rows], total, _open_count(db)

    stmt = select(SecurityIncident)
    count_stmt = select(func.count()).select_from(SecurityIncident)

    if isinstance(status, tuple):
        stmt = stmt.where(SecurityIncident.status.in_(status))
        count_stmt = count_stmt.where(SecurityIncident.status.in_(status))
    elif status:
        stmt = stmt.where(SecurityIncident.status == status)
        count_stmt = count_stmt.where(SecurityIncident.status == status)

    sev = (severity_filter or "").strip().lower()
    if sev:
        stmt = stmt.where(SecurityIncident.severity == sev)
        count_stmt = count_stmt.where(SecurityIncident.severity == sev)

    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(SecurityIncident.created_at.desc(), SecurityIncident.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return [incident_to_read(db, r) for r in rows], total, _open_count(db)


def get_incident_detail(db: Session, incident_id: int) -> dict[str, Any]:
    row = db.get(SecurityIncident, incident_id)
    if row is None:
        raise SecurityToolError("incident_not_found")
    return incident_to_read(db, row)


def run_ids_scan(db: Session, *, include_ai: bool = False) -> dict[str, Any]:
    rules = run_rule_scan(db)
    ai = run_ai_ids_scan(db) if include_ai else 0
    return {
        "rules_incidents": rules,
        "ai_incidents": ai,
        "include_ai": include_ai,
        "open_count": _open_count(db),
    }


def summarize_open_incidents(db: Session, *, limit: int = 50) -> dict[str, Any]:
    items, total, open_count = list_incidents_filtered(
        db, status_filter="active", limit=limit
    )
    by_severity: dict[str, int] = {}
    by_threat: dict[str, int] = {}
    by_status: dict[str, int] = {}
    critical: list[dict[str, Any]] = []
    for row in items:
        sev = str(row.get("severity") or "—")
        threat = str(row.get("threat_type") or "—")
        st = str(row.get("status") or "—")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_threat[threat] = by_threat.get(threat, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
        if sev in {"critical", "high"}:
            critical.append(row)
    return {
        "total_active": total,
        "open_count": open_count,
        "shown": len(items),
        "by_severity": by_severity,
        "by_threat": by_threat,
        "by_status": by_status,
        "critical_samples": critical[:8],
        "incidents": items,
    }


def build_security_report(db: Session, *, hours: int = 24) -> dict[str, Any]:
    """Rapport sécurité déterministe — incidents + signaux logs récents."""
    summary = summarize_open_incidents(db, limit=30)
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
    log_rows = list(
        db.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.created_at >= since,
                or_(
                    ActivityLog.category == "security",
                    ActivityLog.level.in_(("WARNING", "ERROR", "CRITICAL")),
                    ActivityLog.action.like("security.%"),
                ),
            )
            .order_by(ActivityLog.created_at.desc())
            .limit(80)
        ).all()
    )
    login_failures = sum(1 for r in log_rows if "login_failed" in (r.action or ""))
    attack_attempts = sum(1 for r in log_rows if "attack" in (r.action or "") or "probe" in (r.action or ""))
    critical_count = sum(
        1
        for i in summary.get("incidents") or []
        if str(i.get("severity", "")).lower() in {"critical", "high"}
    )
    open_count = int(summary.get("open_count") or 0)
    risk = (
        "élevé"
        if critical_count >= 3 or attack_attempts >= 3
        else "moyen"
        if critical_count or login_failures >= 5
        else "faible"
    )
    return {
        "report_type": "security_report",
        "period_hours": hours,
        "open_incidents_count": open_count,
        "critical_count": critical_count,
        "risk_level": risk,
        "login_failures": login_failures,
        "attack_attempts": attack_attempts,
        "security_logs_analyzed": len(log_rows),
        "summary": summary,
        "recommendations": [
            "Traiter les incidents ouverts en priorité (sévérité critical/high).",
            "Surveiller les tentatives de prompt injection et échecs login.",
            "Vérifier les comptes liés aux incidents non résolus.",
        ],
    }
