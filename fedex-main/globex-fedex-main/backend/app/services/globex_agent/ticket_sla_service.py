"""Service SLA tickets support — détection retards et signaux workspace."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.support_ticket import SupportTicket, SupportTicketStatus

# Heures max avant alerte SLA (statuts actifs uniquement)
_SLA_HOURS: dict[str, int] = {
    "high": 4,
    "urgent": 4,
    "critical": 2,
    "medium": 24,
    "low": 48,
}
_DEFAULT_SLA_HOURS = 24
_ACTIVE_STATUSES = frozenset({
    SupportTicketStatus.open,
    SupportTicketStatus.pending,
    "escalated",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ticket_created_at(ticket: SupportTicket) -> datetime | None:
    ts = ticket.created_at
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def sla_hours_for_priority(priority: str | None) -> int:
    key = str(priority or "medium").lower()
    return _SLA_HOURS.get(key, _DEFAULT_SLA_HOURS)


def ticket_age_hours(ticket: SupportTicket, *, now: datetime | None = None) -> float:
    created = _ticket_created_at(ticket)
    if created is None:
        return 0.0
    ref = now or _now()
    return max(0.0, (ref - created).total_seconds() / 3600.0)


def is_sla_breach(ticket: SupportTicket, *, now: datetime | None = None) -> bool:
    status = ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status or "")
    if status not in _ACTIVE_STATUSES:
        return False
    limit = sla_hours_for_priority(ticket.priority)
    return ticket_age_hours(ticket, now=now) > limit


def scan_sla_breaches(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    """Tickets actifs dépassant le SLA — triés par ancienneté."""
    now = _now()
    rows = list(
        db.scalars(
            select(SupportTicket)
            .where(SupportTicket.status.in_(tuple(_ACTIVE_STATUSES)))
            .order_by(SupportTicket.created_at.asc())
            .limit(100)
        ).all()
    )
    breached: list[dict[str, Any]] = []
    for t in rows:
        if not is_sla_breach(t, now=now):
            continue
        age = ticket_age_hours(t, now=now)
        limit_h = sla_hours_for_priority(t.priority)
        breached.append(
            {
                "ticket_id": t.id,
                "subject": (t.subject or "")[:120],
                "status": t.status.value if hasattr(t.status, "value") else t.status,
                "priority": t.priority,
                "age_hours": round(age, 1),
                "sla_hours": limit_h,
                "overdue_hours": round(age - limit_h, 1),
            }
        )
    breached.sort(key=lambda x: x["overdue_hours"], reverse=True)
    return breached[:limit]


def sla_summary_lines(db: Session) -> list[str]:
    breaches = scan_sla_breaches(db, limit=5)
    if not breaches:
        return []
    lines = [f"{len(breaches)} ticket(s) hors SLA (top priorité)"]
    for b in breaches[:3]:
        lines.append(
            f"#{b['ticket_id']} — {b['subject'][:60]} "
            f"({b['overdue_hours']}h de retard, priorité {b['priority']})"
        )
    return lines
