"""User notification helpers (client_notifications table)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.client_notification import ClientNotification
from app.models.platform_notification import PlatformNotification
from app.models.support_ticket import SupportTicket
from app.models.user import User

NOTIFICATION_TYPES = frozenset(
    {
        "support_message",
        "admin_reply",
        "tracking_update",
        "document_ready",
        "export_ready",
        "system_alert",
        "ai_report",
        "security_alert",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_user_notification(
    db: Session,
    *,
    user_id: int,
    type: str,
    title: str,
    message: str,
    sender_id: int | None = None,
    sender_role: str | None = None,
    priority: str = "medium",
    related_ticket_id: int | None = None,
    related_tracking_number: str = "",
    link: str = "/notifications",
) -> ClientNotification:
    row = ClientNotification(
        user_id=user_id,
        sender_id=sender_id,
        sender_role=sender_role,
        kind=type if type in NOTIFICATION_TYPES else "system_alert",
        title=title[:200],
        message=message,
        priority=priority,
        link=link,
        reference_id=related_ticket_id,
        related_tracking_number=related_tracking_number or "",
        is_read=False,
    )
    db.add(row)
    return row


def notify_admins_new_support_ticket(
    db: Session,
    ticket: SupportTicket,
    user: User,
) -> PlatformNotification:
    preview = ticket.message[:240].replace("\n", " ")
    row = PlatformNotification(
        external_key=f"support-ticket-{ticket.id}",
        category="incidents",
        title="Nouveau message support",
        message=f"{user.full_name or user.email} — {ticket.subject}: {preview}",
        tracking_number="",
        route=f"/admin?section=notifications&ticket={ticket.id}",
        priority="high" if ticket.priority == "high" else "normal",
        channel="web",
        icon="message-circle",
        action_label="Ouvrir",
        action_type="support_ticket",
        action_ref=str(ticket.id),
        is_read=False,
    )
    db.add(row)
    return row


def notify_employees_new_support_ticket(
    db: Session,
    ticket: SupportTicket,
    user: User,
) -> None:
    from sqlalchemy import select

    from app.models.user import UserRole, UserStatus

    employees = list(
        db.scalars(
            select(User).where(User.role == UserRole.employe.value, User.status == UserStatus.active.value)
        ).all()
    )
    preview = ticket.subject[:120]
    from app.services.employee_notification_service import create_employee_notification

    for emp in employees:
        create_employee_notification(
            db,
            employee_id=emp.id,
            type="support_reply",
            title="New support ticket",
            message=f"{user.full_name or user.email} — {preview}",
            related_ticket_id=ticket.id,
            related_client_id=user.id,
            link=f"/employee/support/{ticket.id}",
            priority=ticket.priority or "medium",
        )


def notify_admins_support_user_reply(
    db: Session,
    ticket: SupportTicket,
    user: User,
    preview: str,
) -> PlatformNotification:
    snippet = preview[:240].replace("\n", " ")
    row = PlatformNotification(
        external_key=f"support-reply-{ticket.id}-{int(_now().timestamp())}",
        category="incidents",
        title="Réponse client sur ticket",
        message=f"{user.full_name or user.email} — {ticket.subject}: {snippet}",
        tracking_number="",
        route=f"/admin?section=notifications&ticket={ticket.id}",
        priority="normal",
        channel="web",
        icon="message-circle",
        action_label="Ouvrir",
        action_type="support_ticket",
        action_ref=str(ticket.id),
        is_read=False,
    )
    db.add(row)
    return row


def notification_to_dict(row: ClientNotification) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "sender_id": row.sender_id,
        "sender_role": row.sender_role,
        "type": row.kind,
        "title": row.title,
        "message": row.message,
        "status": "read" if row.is_read else "unread",
        "priority": row.priority or "medium",
        "related_ticket_id": row.reference_id,
        "related_tracking_number": row.related_tracking_number or "",
        "link": row.link,
        "is_read": row.is_read,
        "created_at": row.created_at,
        "read_at": row.read_at,
    }


def maybe_notify_shipment_events(
    db: Session,
    *,
    user_id: int,
    data: dict,
    pod_available: bool = False,
) -> None:
    from app.models.shipment_cache import ShipmentCache

    tn = str(data.get("tracking_number") or "").strip()
    if not tn:
        return

    row = db.query(ShipmentCache).filter(ShipmentCache.tracking_number == tn).one_or_none()
    previous_status = row.last_status if row else None
    new_status = data.get("status")
    location = data.get("current_location") or ""

    if new_status and new_status != previous_status:
        loc_suffix = f" — {location}" if location else ""
        create_user_notification(
            db,
            user_id=user_id,
            type="tracking_update",
            title="Mise à jour de suivi",
            message=f"{new_status}{loc_suffix}",
            related_tracking_number=tn,
            link="/history",
        )
        from app.services.employee_notification_service import notify_employees_tracking_update

        notify_employees_tracking_update(
            db,
            tracking_number=tn,
            status=str(new_status),
            location=location,
        )

    if pod_available and new_status:
        from sqlalchemy import select

        recent = db.scalar(
            select(ClientNotification.id)
            .where(
                ClientNotification.user_id == user_id,
                ClientNotification.kind == "document_ready",
                ClientNotification.related_tracking_number == tn,
            )
            .limit(1)
        )
        if recent is None:
            create_user_notification(
                db,
                user_id=user_id,
                type="document_ready",
                title="Preuve de livraison disponible",
                message=f"Le POD est prêt pour le colis {tn}.",
                related_tracking_number=tn,
                link="/documents",
            )
            from app.services.employee_notification_service import notify_employees_document_uploaded

            notify_employees_document_uploaded(
                db,
                title="Document uploaded",
                message=f"Proof of delivery available for {tn}.",
                related_client_id=user_id,
            )


def maybe_notify_export_ready(db: Session, *, user_id: int, row_count: int) -> None:
    create_user_notification(
        db,
        user_id=user_id,
        type="export_ready",
        title="Export prêt",
        message=f"Votre export Excel ({row_count} lignes) a été généré.",
        link="/history",
    )


def maybe_notify_new_login_device(
    db: Session,
    *,
    user_id: int,
    browser: str,
    machine: str,
    ip: str,
) -> None:
    from app.models.user_session import UserSession
    from app.models.user import UserRole

    known = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.browser == browser,
            UserSession.machine == machine,
        )
        .count()
    )
    if known > 0:
        return
    user = db.get(User, user_id)
    title = "Nouvelle connexion détectée"
    message = f"Connexion depuis {browser} ({machine}) — {ip}"
    if user and user.role == UserRole.employe.value:
        from app.services.employee_notification_service import create_employee_notification

        create_employee_notification(
            db,
            employee_id=user_id,
            type="security_alert",
            title=title,
            message=message,
            priority="high",
            link="/employee?panel=settings&tab=security",
        )
        return
    create_user_notification(
        db,
        user_id=user_id,
        type="security_alert",
        title=title,
        message=message,
        priority="high",
        link="/settings",
    )
