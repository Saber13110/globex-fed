"""Employee portal notifications (client_notifications with role_target=employee)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.client_notification import ClientNotification
from app.models.support_ticket import SupportTicket
from app.models.user import User, UserRole, UserStatus

EMPLOYEE_NOTIFICATION_TYPES = frozenset(
    {
        "support_reply",
        "admin_message",
        "tracking_update",
        "document_uploaded",
        "security_alert",
        "system_alert",
    }
)

SUPPORT_KINDS = frozenset({"support_message", "support_reply", "admin_reply"})
DOCUMENT_KINDS = frozenset({"document_ready", "export_ready", "document_uploaded"})
TRACKING_KINDS = frozenset({"tracking_update", "shipment_update"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_employee_ids(db: Session) -> list[int]:
    return list(
        db.scalars(
            select(User.id).where(
                User.role == UserRole.employe.value,
                User.status == UserStatus.active.value,
            )
        ).all()
    )


def normalize_employee_type(kind: str, link: str = "") -> str:
    k = (kind or "system_alert").lower()
    if k in SUPPORT_KINDS:
        if "/admin-chat" in (link or ""):
            return "admin_message"
        return "support_reply"
    if k in DOCUMENT_KINDS:
        return "document_uploaded"
    if k in TRACKING_KINDS or "tracking" in k:
        return "tracking_update"
    if k == "security_alert":
        return "security_alert"
    if k == "admin_message":
        return "admin_message"
    return "system_alert"


def employee_open_link(
    *,
    notif_type: str,
    link: str = "",
    related_ticket_id: int | None = None,
    related_tracking_number: str = "",
) -> str:
    t = normalize_employee_type(notif_type, link)
    if t == "support_reply" and related_ticket_id:
        return f"/employee/support/{related_ticket_id}"
    if t == "tracking_update" and related_tracking_number:
        return f"/employee/tracking/{related_tracking_number}"
    if t == "document_uploaded":
        return "/employee/documents"
    if t == "admin_message":
        return "/employee/admin-chat"
    if t == "security_alert":
        if link.startswith("/employee/"):
            return link
        if link in ("/settings", "/settings/security"):
            return "/employee?panel=settings&tab=security"
        return "/employee?panel=settings&tab=security"
    if t == "system_alert" and link.startswith("/employee/"):
        return link
    if link.startswith("/employee/"):
        return link
    if link.startswith("/notifications"):
        return "/employee/notifications"
    return link or "/employee/notifications"


def create_employee_notification(
    db: Session,
    *,
    employee_id: int,
    type: str,
    title: str,
    message: str,
    sender_id: int | None = None,
    sender_role: str | None = None,
    priority: str = "medium",
    related_ticket_id: int | None = None,
    related_tracking_number: str = "",
    related_document_id: int | None = None,
    related_client_id: int | None = None,
    link: str | None = None,
) -> ClientNotification:
    normalized = type if type in EMPLOYEE_NOTIFICATION_TYPES else normalize_employee_type(type, link or "")
    resolved_link = link or employee_open_link(
        notif_type=normalized,
        related_ticket_id=related_ticket_id,
        related_tracking_number=related_tracking_number,
    )
    row = ClientNotification(
        user_id=employee_id,
        sender_id=sender_id,
        sender_role=sender_role,
        kind=normalized,
        title=title[:200],
        message=message,
        priority=priority,
        link=resolved_link,
        reference_id=related_ticket_id,
        related_tracking_number=related_tracking_number or "",
        related_document_id=related_document_id,
        related_client_id=related_client_id,
        role_target="employee",
        is_read=False,
    )
    db.add(row)
    return row


def ticket_assigned_employee_id(ticket: SupportTicket) -> int | None:
    for msg in reversed(ticket.messages or []):
        if msg.author_role in ("employe", "employee") and msg.author_user_id:
            return msg.author_user_id
    return None


def notify_employee_ticket_admin_reply(
    db: Session,
    *,
    ticket: SupportTicket,
    admin_id: int,
    body: str,
) -> None:
    assigned = ticket_assigned_employee_id(ticket)
    targets = [assigned] if assigned else _active_employee_ids(db)
    preview = body[:500]
    for emp_id in targets:
        create_employee_notification(
            db,
            employee_id=emp_id,
            type="support_reply",
            title="Admin replied to support ticket",
            message=f"{ticket.subject}: {preview[:160]}",
            sender_id=admin_id,
            sender_role="admin",
            priority=ticket.priority or "medium",
            related_ticket_id=ticket.id,
            related_client_id=ticket.user_id,
        )


def notify_employees_ticket_user_reply(
    db: Session,
    *,
    ticket: SupportTicket,
    user: User,
    body: str,
) -> None:
    assigned = ticket_assigned_employee_id(ticket)
    targets = [assigned] if assigned else _active_employee_ids(db)
    preview = body[:500]
    name = user.full_name or user.email
    for emp_id in targets:
        create_employee_notification(
            db,
            employee_id=emp_id,
            type="support_reply",
            title="Customer replied to ticket",
            message=f"{name} — {ticket.subject}: {preview[:120]}",
            sender_id=user.id,
            sender_role="user",
            priority=ticket.priority or "medium",
            related_ticket_id=ticket.id,
            related_client_id=user.id,
        )


def notify_employee_admin_message(
    db: Session,
    *,
    employee_id: int,
    admin_id: int,
    body: str,
) -> None:
    create_employee_notification(
        db,
        employee_id=employee_id,
        type="admin_message",
        title="Message from administrator",
        message=body[:500],
        sender_id=admin_id,
        sender_role="admin",
        priority="high",
        link="/employee/admin-chat",
    )


def notify_employees_tracking_update(
    db: Session,
    *,
    tracking_number: str,
    status: str,
    location: str = "",
) -> None:
    loc_suffix = f" — {location}" if location else ""
    message = f"{tracking_number}: {status}{loc_suffix}"
    for emp_id in _active_employee_ids(db):
        create_employee_notification(
            db,
            employee_id=emp_id,
            type="tracking_update",
            title="Shipment status updated",
            message=message,
            related_tracking_number=tracking_number,
            priority="medium",
        )


def notify_employees_document_uploaded(
    db: Session,
    *,
    title: str,
    message: str,
    related_document_id: int | None = None,
    related_client_id: int | None = None,
) -> None:
    for emp_id in _active_employee_ids(db):
        create_employee_notification(
            db,
            employee_id=emp_id,
            type="document_uploaded",
            title=title,
            message=message,
            related_document_id=related_document_id,
            related_client_id=related_client_id,
            link="/employee/documents",
        )


def _employee_notifications_query(employee_id: int):
    return select(ClientNotification).where(
        ClientNotification.user_id == employee_id,
        or_(
            ClientNotification.role_target == "employee",
            ClientNotification.role_target.is_(None),
        ),
    )


def employee_notification_stats(db: Session, employee_id: int) -> dict[str, int]:
    rows = list(db.scalars(_employee_notifications_query(employee_id)).all())
    stats = {"all": 0, "unread": 0, "support": 0, "tracking": 0, "documents": 0, "security": 0}
    for row in rows:
        stats["all"] += 1
        if not row.is_read:
            stats["unread"] += 1
        t = normalize_employee_type(row.kind, row.link)
        if t == "support_reply":
            stats["support"] += 1
        elif t == "tracking_update":
            stats["tracking"] += 1
        elif t == "document_uploaded":
            stats["documents"] += 1
        elif t == "security_alert":
            stats["security"] += 1
    return stats


def employee_notification_to_dict(row: ClientNotification) -> dict:
    ntype = normalize_employee_type(row.kind, row.link)
    return {
        "id": row.id,
        "type": ntype,
        "kind": ntype,
        "title": row.title,
        "message": row.message,
        "status": "read" if row.is_read else "unread",
        "link": employee_open_link(
            notif_type=ntype,
            link=row.link,
            related_ticket_id=row.reference_id,
            related_tracking_number=row.related_tracking_number or "",
        ),
        "is_read": row.is_read,
        "related_ticket_id": row.reference_id,
        "related_tracking_number": row.related_tracking_number or "",
        "related_document_id": row.related_document_id,
        "related_client_id": row.related_client_id,
        "created_at": row.created_at,
        "read_at": row.read_at,
    }
