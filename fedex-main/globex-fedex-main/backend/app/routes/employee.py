"""Routes portail employé — accès opérationnel sans privilèges admin sensibles."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import cast, func, or_, select, String
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.client_notification import ClientNotification
from app.models.employee_admin_message import EmployeeAdminMessage
from app.models.platform_notification import PlatformNotification
from app.models.report_run import ReportRun
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.support_ticket_message import SupportTicketMessage
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole, UserStatus
from app.models.user_session import UserSession
from app.core.security import decode_access_token
from app.routes.deps import get_current_user, require_role
from app.schemas.employee import (
    EmployeeAdminChatConversation,
    EmployeeAdminChatParticipant,
    EmployeeAdminChatSearchHit,
    EmployeeAdminChatSearchResponse,
    EmployeeAdminChatSharedFile,
    EmployeeAdminChatTyping,
    EmployeeAdminChatWorkspace,
    EmployeeAdminChatResponse,
    AdminEmployeeChatListItem,
    EmployeeAdminMessageCreate,
    EmployeeAdminMessageRead,
    EmployeeAiAction,
    EmployeeAiAgentCard,
    EmployeeAiAgentCardAction,
    EmployeeAiAgentConversationCreate,
    EmployeeAiAgentConversationDetail,
    EmployeeAiAgentConversationSummary,
    EmployeeAiAgentConversationUpdate,
    EmployeeAiAgentLiveContext,
    EmployeeAiAgentMessageRead,
    EmployeeAiAgentMessageRequest,
    EmployeeAiAgentMessageResponse,
    EmployeeAiClientResult,
    EmployeeAiDocumentResult,
    EmployeeAiRequest,
    EmployeeAiResponse,
    EmployeeAiTicketResult,
    EmployeeAiTrackingEvent,
    EmployeeAiTrackingResult,
    EmployeeChatContextPanel,
    EmployeeClientDetail,
    EmployeeClientListResponse,
    EmployeeClientOpsStats,
    EmployeeClientActivityEvent,
    EmployeeClientSummary,
    EmployeeDashboardAdminComm,
    EmployeeDashboardClientWidget,
    EmployeeDashboardStats,
    EmployeeDashboardTicketWidget,
    EmployeeDashboardTrackingEvent,
    EmployeeDashboardTrackingSummary,
    EmployeeDashboardWorkspace,
    EmployeeHelpdeskAssign,
    EmployeeHelpdeskEmployeeOption,
    EmployeeHelpdeskInternalNote,
    EmployeeHelpdeskMessageRead,
    EmployeeHelpdeskStats,
    EmployeeHelpdeskTicketDetail,
    EmployeeHelpdeskTicketListResponse,
    EmployeeHelpdeskTicketSummary,
    EmployeeDocumentItem,
    EmployeeMetricCard,
    EmployeeNotificationListResponse,
    EmployeeNotificationRead,
    EmployeeNotificationStats,
    EmployeeSearchHit,
    EmployeeSearchResponse,
    EmployeeSettingsRead,
    EmployeeSettingsUpdate,
    EmployeeShipmentDetail,
    EmployeeShipmentExceptionInfo,
    EmployeeShipmentHealth,
    EmployeeShipmentListResponse,
    EmployeeShipmentMapPoint,
    EmployeeShipmentRelatedClient,
    EmployeeShipmentTimelineEvent,
    EmployeeTrackingItem,
    EmployeeTrackingOpsStats,
)
from app.schemas.support import (
    SupportMessageCreate,
    SupportTicketListResponse,
    SupportTicketRead,
    SupportTicketStatusUpdate,
)
from app.models.ai_agent_message import AiAgentMessage
from app.services import ai_agent_service, fedex_service, llm_service
from app.services.proof_of_delivery_service import get_proof_of_delivery_pdf, is_likely_delivered
from app.services.reports_service import get_run_file
from app.services.activity_log_service import client_ip, write_log
from app.services.help_center_service import generate_ticket_number
from app.services.employee_admin_chat_hub import employee_admin_chat_hub
from app.services.employee_notification_service import (
    create_employee_notification,
    employee_notification_stats,
    employee_notification_to_dict,
    employee_open_link,
    normalize_employee_type,
    notify_employee_admin_message,
    notify_employee_ticket_admin_reply,
    notify_employees_document_uploaded,
    notify_employees_ticket_user_reply,
    notify_employees_tracking_update,
)
from app.services.user_notification_service import create_user_notification
from app.routes.support import _message_allowed, _sanitize_text, _ticket_to_read

router = APIRouter(prefix="/api/employee", tags=["employee"])

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_summary(db: Session, user: User) -> EmployeeClientSummary:
    open_tickets = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.user_id == user.id, SupportTicket.status.in_(("open", "pending", "escalated")))
        )
        or 0
    )
    recent_trackings = int(
        db.scalar(
            select(func.count())
            .select_from(TrackingRequest)
            .where(TrackingRequest.user_id == user.id)
        )
        or 0
    )
    documents_count = int(
        db.scalar(
            select(func.count()).select_from(ReportRun).where(ReportRun.generated_by_user_id == user.id)
        )
        or 0
    )
    active_shipments = int(
        db.scalar(
            select(func.count())
            .select_from(TrackingRequest)
            .where(
                TrackingRequest.user_id == user.id,
                ~func.lower(TrackingRequest.status).in_(("delivered", "livré", "cancelled", "annulé")),
            )
        )
        or 0
    )
    last_tr = db.scalar(
        select(TrackingRequest)
        .where(TrackingRequest.user_id == user.id)
        .order_by(TrackingRequest.created_at.desc())
        .limit(1)
    )
    last_activity = "No recent activity"
    if last_tr:
        last_activity = f"{last_tr.tracking_number} · {last_tr.status or '—'}"
    exception_count = int(
        db.scalar(
            select(func.count())
            .select_from(TrackingRequest)
            .where(
                TrackingRequest.user_id == user.id,
                or_(
                    func.lower(TrackingRequest.status).like("%exception%"),
                    func.lower(TrackingRequest.status).like("%delay%"),
                ),
            )
        )
        or 0
    )
    return EmployeeClientSummary(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        status=user.status,
        preferred_language=user.preferred_language,
        created_at=user.created_at,
        open_tickets=open_tickets,
        recent_trackings=recent_trackings,
        documents_count=documents_count,
        company=_company_label(user),
        avatar_initials=_initials(user.full_name),
        last_activity=last_activity,
        pending_issues=open_tickets + exception_count,
        active_shipments=active_shipments,
    )


def _client_last_login(db: Session, user_id: int) -> datetime | None:
    return db.scalar(
        select(UserSession.updated_at)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.updated_at.desc())
        .limit(1)
    )


def _client_assigned_employee(db: Session, client_id: int) -> str:
    name = db.scalar(
        select(User.full_name)
        .select_from(SupportTicketMessage)
        .join(SupportTicket, SupportTicket.id == SupportTicketMessage.ticket_id)
        .join(User, User.id == SupportTicketMessage.author_user_id)
        .where(
            SupportTicket.user_id == client_id,
            SupportTicketMessage.author_role.in_(("employe", "admin", "employee")),
        )
        .order_by(SupportTicketMessage.created_at.desc())
        .limit(1)
    )
    if name:
        return name
    fallback = db.scalar(
        select(User.full_name)
        .where(User.role == UserRole.employe.value, User.status == UserStatus.active.value)
        .order_by(User.id.asc())
        .limit(1)
    )
    return fallback or "GlobeX Operations"


def _client_activity_events(db: Session, client_id: int, limit: int = 50) -> list[EmployeeClientActivityEvent]:
    events: list[EmployeeClientActivityEvent] = []

    for tr in db.scalars(
        select(TrackingRequest)
        .where(TrackingRequest.user_id == client_id)
        .order_by(TrackingRequest.created_at.desc())
        .limit(25)
    ).all():
        events.append(
            EmployeeClientActivityEvent(
                id=f"tracking-{tr.id}",
                kind="shipment",
                title=f"Shipment {tr.tracking_number}",
                description=tr.status or "Created",
                created_at=tr.created_at,
            )
        )

    for r in db.scalars(
        select(ReportRun)
        .where(ReportRun.generated_by_user_id == client_id)
        .order_by(ReportRun.created_at.desc())
        .limit(15)
    ).all():
        events.append(
            EmployeeClientActivityEvent(
                id=f"document-{r.id}",
                kind="document",
                title=f"Document {r.name}",
                description=r.format or "Uploaded",
                created_at=r.created_at,
            )
        )

    for tk in db.scalars(
        select(SupportTicket)
        .where(SupportTicket.user_id == client_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(15)
    ).all():
        num = tk.ticket_number or generate_ticket_number(tk.id)
        events.append(
            EmployeeClientActivityEvent(
                id=f"ticket-{tk.id}",
                kind="ticket",
                title=f"Ticket {num}",
                description=tk.subject,
                created_at=tk.created_at,
            )
        )

    for msg in db.scalars(
        select(SupportTicketMessage)
        .join(SupportTicket, SupportTicket.id == SupportTicketMessage.ticket_id)
        .where(
            SupportTicket.user_id == client_id,
            SupportTicketMessage.author_role.in_(("employe", "admin", "employee")),
        )
        .order_by(SupportTicketMessage.created_at.desc())
        .limit(15)
    ).all():
        events.append(
            EmployeeClientActivityEvent(
                id=f"reply-{msg.id}",
                kind="support_reply",
                title="Support reply",
                description=msg.body[:120],
                created_at=msg.created_at,
            )
        )

    for n in db.scalars(
        select(ClientNotification)
        .where(ClientNotification.user_id == client_id)
        .order_by(ClientNotification.created_at.desc())
        .limit(15)
    ).all():
        kind = "tracking_update" if "tracking" in (n.kind or "") else "notification"
        events.append(
            EmployeeClientActivityEvent(
                id=f"notif-{n.id}",
                kind=kind,
                title=n.title,
                description=n.message[:120],
                created_at=n.created_at,
            )
        )

    events.sort(key=lambda e: e.created_at, reverse=True)
    return events[:limit]


def _notify_employee(
    db: Session,
    *,
    employee_id: int,
    kind: str,
    title: str,
    message: str,
    link: str = "/employee/notifications",
    sender_id: int | None = None,
) -> None:
    create_employee_notification(
        db,
        employee_id=employee_id,
        type=kind,
        title=title,
        message=message,
        link=link,
        sender_id=sender_id,
        sender_role="admin" if sender_id else None,
    )


def _notify_admins_employee_message(db: Session, employee: User, preview: str) -> None:
    key = f"employee-admin-chat-{employee.id}-{int(_now().timestamp())}"
    row = PlatformNotification(
        external_key=key,
        category="incidents",
        title="Message employé",
        message=f"{employee.full_name or employee.email}: {preview[:240]}",
        route=f"/admin?section=notifications&employee={employee.id}",
        priority="normal",
        channel="web",
        icon="message-circle",
        action_label="Répondre",
        action_type="employee_chat",
        action_ref=str(employee.id),
    )
    db.add(row)


def _trend(current: int, previous: int) -> tuple[str, bool]:
    if previous == 0:
        return (f"+{current}" if current > 0 else "0%", current >= 0)
    pct = int(round((current - previous) / previous * 100))
    return (f"{pct:+d}%", pct >= 0)


def _initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _company_label(user: User) -> str:
    if user.email and "@" in user.email:
        domain = user.email.split("@", 1)[1]
        return domain.split(".")[0].capitalize()
    return user.organization_id[:8] if user.organization_id else "Client"


def _is_tracking_exception(status: str | None) -> bool:
    s = (status or "").lower()
    return any(k in s for k in ("exception", "delay", "retard", "hold", "hold", "failed", "échec"))


def _is_tracking_delayed(status: str | None) -> bool:
    s = (status or "").lower()
    return any(k in s for k in ("delay", "retard", "late", "pending"))


def _status_category(status: str | None) -> str:
    s = (status or "").lower()
    if any(k in s for k in ("delivered", "livré", "delivery complete")):
        return "delivered"
    if _is_tracking_exception(s):
        return "exception"
    if any(k in s for k in ("ready for pickup", "hold at location", "available for pickup", "pickup")):
        return "ready_for_pickup"
    if any(k in s for k in ("transit", "route", "departed", "arrived", "hub", "en route", "out for delivery")):
        return "in_transit"
    return "pending"


_CITY_COORDS: dict[str, tuple[float, float]] = {
    "paris": (48.8566, 2.3522),
    "casablanca": (33.5731, -7.5898),
    "lyon": (45.764, 4.8357),
    "marseille": (43.2965, 5.3698),
    "new york": (40.7128, -74.006),
    "memphis": (35.1495, -90.049),
    "dubai": (25.2048, 55.2708),
    "london": (51.5074, -0.1278),
    "rabat": (34.0209, -6.8416),
    "marrakech": (31.6295, -7.9811),
}


def _geocode_location(location: str) -> tuple[float, float] | None:
    loc = (location or "").lower()
    for city, coords in _CITY_COORDS.items():
        if city in loc:
            return coords
    return None


def _parse_event_datetime(raw: str) -> tuple[str, str]:
    if not raw:
        return ("—", "—")
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"))
    except ValueError:
        return (raw[:10] if len(raw) >= 10 else raw, "")


def _timeline_kind(description: str) -> str:
    d = (description or "").lower()
    if any(k in d for k in ("delivered", "livré", "delivery")):
        return "delivered"
    if any(k in d for k in ("out for delivery",)):
        return "out_for_delivery"
    if any(k in d for k in ("pickup", "hold at location")):
        return "pickup"
    if any(k in d for k in ("exception", "delay", "retard")):
        return "exception"
    if any(k in d for k in ("created", "picked up", "pris en charge", "label created")):
        return "created"
    if any(k in d for k in ("arrived", "facility", "hub")):
        return "facility"
    return "transit"


def _tracking_item_from_row(row: TrackingRequest, users: dict[int, User]) -> EmployeeTrackingItem:
    u = users.get(row.user_id)
    status = row.status or ""
    return EmployeeTrackingItem(
        id=row.id,
        tracking_number=row.tracking_number,
        status=status,
        current_location=row.current_location or "",
        estimated_delivery=row.estimated_delivery or "",
        user_question=row.user_question or "",
        created_at=row.created_at,
        client_name=u.full_name if u else None,
        client_id=row.user_id,
        status_category=_status_category(status),
        is_exception=_is_tracking_exception(status),
    )


def _build_shipment_detail(db: Session, tracking_number: str) -> EmployeeShipmentDetail:
    normalized = fedex_service.normalize_tracking_number(tracking_number)
    row = db.scalar(
        select(TrackingRequest)
        .where(func.lower(TrackingRequest.tracking_number) == normalized.lower())
        .order_by(TrackingRequest.created_at.desc())
        .limit(1)
    )
    client: User | None = db.get(User, row.user_id) if row else None

    status = row.status if row else ""
    location = row.current_location if row else ""
    eta = row.estimated_delivery if row else ""
    weight = ""
    dimensions = ""
    fedex_events: list[dict] = []

    try:
        data = fedex_service.get_shipment(normalized)
        status = str(data.get("status") or status or "Unknown")
        location = str(data.get("current_location") or location or "—")
        eta = str(data.get("estimated_delivery") or eta or "—")
        weight = str(data.get("weight") or "")
        dimensions = str(data.get("dimensions") or "")
        fedex_events = list(data.get("events") or [])
    except fedex_service.TrackingLookupError:
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colis introuvable.") from None
        status = status or "Unknown"
        location = location or "—"
        eta = eta or "—"

    timeline: list[EmployeeShipmentTimelineEvent] = []
    for idx, ev in enumerate(fedex_events):
        desc = str(ev.get("description") or "Tracking event")
        loc = str(ev.get("location") or location or "—")
        date_str, time_str = _parse_event_datetime(str(ev.get("at") or ""))
        timeline.append(
            EmployeeShipmentTimelineEvent(
                id=f"ev-{idx}",
                date=date_str,
                time=time_str,
                location=loc,
                description=desc,
                kind=_timeline_kind(desc),
            )
        )

    if not timeline and row:
        date_str, time_str = _parse_event_datetime(str(row.created_at))
        timeline.append(
            EmployeeShipmentTimelineEvent(
                id="ev-created",
                date=date_str,
                time=time_str,
                location=location or "—",
                description="Shipment Created",
                kind="created",
            )
        )
        if status:
            timeline.insert(
                0,
                EmployeeShipmentTimelineEvent(
                    id="ev-status",
                    date=date_str,
                    time=time_str,
                    location=location or "—",
                    description=status,
                    kind=_timeline_kind(status),
                ),
            )

    map_points: list[EmployeeShipmentMapPoint] = []
    seen_coords: set[tuple[float, float]] = set()
    for ev in timeline:
        coords = _geocode_location(ev.location)
        if coords and coords not in seen_coords:
            seen_coords.add(coords)
            map_points.append(
                EmployeeShipmentMapPoint(
                    label=ev.location,
                    lat=coords[0],
                    lng=coords[1],
                    kind="history" if len(map_points) > 0 else "current",
                )
            )
    if map_points:
        map_points[-1].kind = "current"
        if len(map_points) > 1:
            map_points[0].kind = "destination"

    exception: EmployeeShipmentExceptionInfo | None = None
    if _is_tracking_exception(status):
        exception = EmployeeShipmentExceptionInfo(
            exception_type="Shipment Exception",
            reason=status,
            priority="high" if "delay" in status.lower() or "retard" in status.lower() else "medium",
            detected_at=row.created_at if row else None,
        )

    recipient = client.full_name if client else "—"
    destination = timeline[0].location if timeline else location
    last_update = f"{timeline[0].date} {timeline[0].time}".strip() if timeline else "—"
    status_cat = _status_category(status)
    pod_available = status_cat == "delivered" or is_likely_delivered(status, fedex_events)

    related_client: EmployeeShipmentRelatedClient | None = None
    if client:
        summary = _client_summary(db, client)
        related_client = EmployeeShipmentRelatedClient(
            id=client.id,
            full_name=client.full_name,
            email=client.email,
            avatar_initials=summary.avatar_initials,
            trackings_count=summary.recent_trackings,
            tickets_count=summary.open_tickets,
            documents_count=summary.documents_count,
        )

    risk = "low"
    if _is_tracking_exception(status):
        risk = "high"
    elif _is_tracking_delayed(status):
        risk = "medium"
    health = EmployeeShipmentHealth(
        status=status,
        risk=risk,
        exception=_is_tracking_exception(status),
        pod=pod_available,
    )

    return EmployeeShipmentDetail(
        tracking_number=normalized,
        status=status,
        status_category=status_cat,
        current_location=location,
        recipient=recipient,
        last_update=last_update,
        estimated_delivery=eta,
        reference_number=normalized,
        service_type="FedEx Express",
        weight=weight or "—",
        dimensions=dimensions or "—",
        sender=_company_label(client) if client else "GlobeX Shipper",
        destination=destination or "—",
        client_id=client.id if client else None,
        client_name=client.full_name if client else "",
        client_email=client.email if client else "",
        timeline=timeline,
        map_points=map_points,
        exception=exception,
        pod_available=pod_available,
        related_client=related_client,
        health=health,
    )


@router.get("/dashboard", response_model=EmployeeDashboardWorkspace)
def employee_dashboard(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeDashboardWorkspace:
    now = _now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    open_tickets = int(
        db.scalar(
            select(func.count()).select_from(SupportTicket).where(SupportTicket.status == SupportTicketStatus.open)
        )
        or 0
    )
    pending_tickets = int(
        db.scalar(
            select(func.count()).select_from(SupportTicket).where(SupportTicket.status == SupportTicketStatus.pending)
        )
        or 0
    )
    pending_escalations = int(
        db.scalar(
            select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "escalated")
        )
        or 0
    )
    total_clients = int(
        db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.client.value)) or 0
    )
    active_clients = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.client.value, User.status == UserStatus.active.value)
        )
        or 0
    )
    unread_notifications = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == employee.id, ClientNotification.is_read.is_(False))
        )
        or 0
    )
    unread_admin_messages = int(
        db.scalar(
            select(func.count())
            .select_from(EmployeeAdminMessage)
            .where(
                EmployeeAdminMessage.employee_id == employee.id,
                EmployeeAdminMessage.sender_role == "admin",
                EmployeeAdminMessage.is_read.is_(False),
            )
        )
        or 0
    )
    recent_trackings = int(db.scalar(select(func.count()).select_from(TrackingRequest)) or 0)

    all_trackings = list(db.scalars(select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(200)).all())
    exception_count = sum(1 for t in all_trackings if _is_tracking_exception(t.status))
    delayed_count = sum(1 for t in all_trackings if _is_tracking_delayed(t.status))
    active_tracking_count = sum(
        1
        for t in all_trackings
        if (t.status or "").lower() not in ("delivered", "livré", "cancelled", "annulé")
    )

    documents_processed = int(db.scalar(select(func.count()).select_from(ReportRun)) or 0) + sum(
        1 for t in all_trackings if (t.status or "").lower() in ("delivered", "livré")
    )

    pending_actions = pending_tickets + pending_escalations + unread_admin_messages

    unread_tickets = _count_unread_helpdesk_tickets(db)

    stats = EmployeeDashboardStats(
        open_tickets=open_tickets,
        pending_tickets=pending_tickets,
        total_clients=total_clients,
        unread_notifications=unread_notifications,
        unread_admin_messages=unread_admin_messages,
        recent_trackings=recent_trackings,
        active_clients=active_clients,
        tracking_exceptions=exception_count,
        pending_escalations=pending_escalations,
        documents_processed=documents_processed,
        pending_actions=pending_actions,
        unread_tickets=unread_tickets,
    )

    tickets_this_week = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.created_at >= week_ago)
        )
        or 0
    )
    tickets_prev_week = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.created_at >= two_weeks_ago, SupportTicket.created_at < week_ago)
        )
        or 0
    )
    clients_this_week = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.client.value, User.created_at >= week_ago)
        )
        or 0
    )
    clients_prev_week = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.client.value,
                User.created_at >= two_weeks_ago,
                User.created_at < week_ago,
            )
        )
        or 0
    )

    t_open, t_open_up = _trend(open_tickets + pending_tickets, tickets_prev_week)
    t_clients, t_clients_up = _trend(active_clients, clients_prev_week)
    t_exceptions, t_exceptions_up = _trend(exception_count, max(exception_count - 1, 0))
    t_pending, t_pending_up = _trend(pending_actions, max(pending_actions - 1, 0))
    t_track, t_track_up = _trend(active_tracking_count, max(active_tracking_count - 2, 0))
    t_docs, t_docs_up = _trend(documents_processed, max(documents_processed - 5, 0))

    metrics = [
        EmployeeMetricCard(key="active_clients", value=active_clients, label="Active Clients", trend=t_clients, trend_up=t_clients_up, icon="users"),
        EmployeeMetricCard(key="open_tickets", value=open_tickets, label="Open Tickets", trend=t_open, trend_up=t_open_up, icon="ticket"),
        EmployeeMetricCard(key="tracking_exceptions", value=exception_count, label="Tracking Exceptions", trend=t_exceptions, trend_up=not t_exceptions_up, icon="alert"),
        EmployeeMetricCard(key="pending_actions", value=pending_actions, label="Pending Actions", trend=t_pending, trend_up=t_pending_up, icon="clipboard"),
        EmployeeMetricCard(key="tracking_ops", value=active_tracking_count, label="Tracking Operations", trend=t_track, trend_up=t_track_up, icon="package"),
        EmployeeMetricCard(key="documents", value=documents_processed, label="Documents Processed", trend=t_docs, trend_up=t_docs_up, icon="file"),
    ]

    client_rows = list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.client.value)
            .order_by(User.created_at.desc())
            .limit(5)
        ).all()
    )
    recent_clients: list[EmployeeDashboardClientWidget] = []
    for c in client_rows:
        last_tr = db.scalar(
            select(TrackingRequest)
            .where(TrackingRequest.user_id == c.id)
            .order_by(TrackingRequest.created_at.desc())
            .limit(1)
        )
        open_tk = int(
            db.scalar(
                select(func.count())
                .select_from(SupportTicket)
                .where(
                    SupportTicket.user_id == c.id,
                    SupportTicket.status.in_(("open", "pending", "escalated")),
                )
            )
            or 0
        )
        activity = "No recent activity"
        if last_tr:
            activity = f"{last_tr.tracking_number} · {last_tr.status or '—'}"
        recent_clients.append(
            EmployeeDashboardClientWidget(
                id=c.id,
                full_name=c.full_name,
                company=_company_label(c),
                email=c.email,
                last_activity=activity,
                avatar_initials=_initials(c.full_name),
                open_tickets=open_tk,
            )
        )

    ticket_rows = list(
        db.scalars(
            select(SupportTicket)
            .options(joinedload(SupportTicket.user))
            .order_by(SupportTicket.created_at.desc())
            .limit(5)
        ).all()
    )
    recent_tickets = [
        EmployeeDashboardTicketWidget(
            id=t.id,
            ticket_number=t.ticket_number or generate_ticket_number(t.id),
            subject=t.subject,
            priority=t.priority or "medium",
            status=t.status,
            client_name=t.user.full_name if t.user else "—",
            created_at=t.created_at,
        )
        for t in ticket_rows
    ]

    client_user_ids = set(
        db.scalars(select(User.id).where(User.role == UserRole.client.value)).all()
    )
    client_trackings = [t for t in all_trackings if t.user_id in client_user_ids]
    tr_user_ids = {t.user_id for t in client_trackings[:10]}
    tr_users = {
        u.id: u
        for u in db.scalars(select(User).where(User.id.in_(tr_user_ids))).all()
    } if tr_user_ids else {}
    latest_events = [
        EmployeeDashboardTrackingEvent(
            tracking_number=t.tracking_number,
            status=t.status or "—",
            client_name=tr_users[t.user_id].full_name if t.user_id in tr_users else "—",
            created_at=t.created_at,
            is_exception=_is_tracking_exception(t.status),
        )
        for t in client_trackings[:6]
    ]
    tracking_summary = EmployeeDashboardTrackingSummary(
        delayed_count=delayed_count,
        exception_count=exception_count,
        active_count=active_tracking_count,
        latest_events=latest_events,
    )

    latest_admin_msg = db.scalar(
        select(EmployeeAdminMessage)
        .where(EmployeeAdminMessage.employee_id == employee.id, EmployeeAdminMessage.sender_role == "admin")
        .order_by(EmployeeAdminMessage.created_at.desc())
        .limit(1)
    )
    latest_announcement = db.scalar(
        select(PlatformNotification)
        .where(PlatformNotification.category.in_(("incidents", "system")))
        .order_by(PlatformNotification.created_at.desc())
        .limit(1)
    )
    admin_comm = EmployeeDashboardAdminComm(
        unread_count=unread_admin_messages,
        latest_message=latest_admin_msg.body[:240] if latest_admin_msg else "",
        latest_sender="Administrator" if latest_admin_msg else "",
        latest_at=latest_admin_msg.created_at if latest_admin_msg else None,
        latest_announcement=latest_announcement.message[:200] if latest_announcement else "",
    )

    notif_rows = list(
        db.scalars(
            select(ClientNotification)
            .where(ClientNotification.user_id == employee.id)
            .order_by(ClientNotification.created_at.desc())
            .limit(5)
        ).all()
    )
    recent_notifications = []
    for n in notif_rows:
        payload = employee_notification_to_dict(n)
        payload["message"] = payload["message"][:180]
        recent_notifications.append(EmployeeNotificationRead.model_validate(payload))

    return EmployeeDashboardWorkspace(
        stats=stats,
        metrics=metrics,
        recent_clients=recent_clients,
        recent_tickets=recent_tickets,
        tracking_summary=tracking_summary,
        admin_communication=admin_comm,
        recent_notifications=recent_notifications,
    )


@router.get("/search", response_model=EmployeeSearchResponse)
def employee_search(
    q: str = Query(min_length=1, max_length=120),
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeSearchResponse:
    term = f"%{q.strip().lower()}%"
    hits: list[EmployeeSearchHit] = []

    clients = list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.client.value)
            .where(or_(func.lower(User.full_name).like(term), func.lower(User.email).like(term)))
            .limit(8)
        ).all()
    )
    for c in clients:
        hits.append(
            EmployeeSearchHit(
                kind="client",
                id=str(c.id),
                title=c.full_name,
                subtitle=c.email,
                link=f"/employee/client/{c.id}",
            )
        )

    trackings = list(
        db.scalars(
            select(TrackingRequest)
            .where(func.lower(TrackingRequest.tracking_number).like(term))
            .order_by(TrackingRequest.created_at.desc())
            .limit(8)
        ).all()
    )
    for t in trackings:
        hits.append(
            EmployeeSearchHit(
                kind="tracking",
                id=str(t.id),
                title=t.tracking_number,
                subtitle=t.status or "—",
                link=f"/employee/tracking/{t.tracking_number}",
            )
        )

    tickets = list(
        db.scalars(
            select(SupportTicket)
            .where(
                or_(
                    func.lower(SupportTicket.subject).like(term),
                    func.lower(SupportTicket.ticket_number).like(term),
                    func.lower(SupportTicket.message).like(term),
                )
            )
            .order_by(SupportTicket.created_at.desc())
            .limit(8)
        ).all()
    )
    for tk in tickets:
        num = tk.ticket_number or generate_ticket_number(tk.id)
        hits.append(
            EmployeeSearchHit(
                kind="ticket",
                id=str(tk.id),
                title=tk.subject,
                subtitle=num,
                link=f"/employee/support/{tk.id}",
            )
        )

    notifs = list(
        db.scalars(
            select(ClientNotification)
            .where(or_(func.lower(ClientNotification.title).like(term), func.lower(ClientNotification.message).like(term)))
            .order_by(ClientNotification.created_at.desc())
            .limit(5)
        ).all()
    )
    for n in notifs:
        hits.append(
            EmployeeSearchHit(
                kind="notification",
                id=str(n.id),
                title=n.title,
                subtitle=n.kind,
                link="/employee/notifications",
            )
        )

    reports = list(
        db.scalars(
            select(ReportRun)
            .where(func.lower(ReportRun.name).like(term))
            .order_by(ReportRun.created_at.desc())
            .limit(5)
        ).all()
    )
    for r in reports:
        hits.append(
            EmployeeSearchHit(
                kind="document",
                id=str(r.id),
                title=r.name,
                subtitle=r.format,
                link="/employee/clients",
            )
        )

    return EmployeeSearchResponse(query=q.strip(), items=hits[:30])


@router.get("/clients/stats", response_model=EmployeeClientOpsStats)
def clients_ops_stats(
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeClientOpsStats:
    now = _now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    total_clients = int(
        db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.client.value)) or 0
    )
    active_clients = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.client.value, User.status == UserStatus.active.value)
        )
        or 0
    )
    open_tickets = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status.in_(("open", "pending", "escalated")))
        )
        or 0
    )
    active_shipments = int(
        db.scalar(
            select(func.count())
            .select_from(TrackingRequest)
            .where(
                ~func.lower(TrackingRequest.status).in_(("delivered", "livré", "cancelled", "annulé")),
            )
        )
        or 0
    )
    recent_documents = int(
        db.scalar(
            select(func.count()).select_from(ReportRun).where(ReportRun.created_at >= week_ago)
        )
        or 0
    )
    pending_issues = open_tickets + int(
        db.scalar(
            select(func.count())
            .select_from(TrackingRequest)
            .where(
                or_(
                    func.lower(TrackingRequest.status).like("%exception%"),
                    func.lower(TrackingRequest.status).like("%delay%"),
                )
            )
        )
        or 0
    )

    clients_prev_week = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.client.value,
                User.created_at >= two_weeks_ago,
                User.created_at < week_ago,
            )
        )
        or 0
    )
    tickets_prev_week = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.created_at >= two_weeks_ago, SupportTicket.created_at < week_ago)
        )
        or 0
    )
    docs_prev_week = int(
        db.scalar(
            select(func.count())
            .select_from(ReportRun)
            .where(ReportRun.created_at >= two_weeks_ago, ReportRun.created_at < week_ago)
        )
        or 0
    )

    t_total, t_total_up = _trend(total_clients, max(total_clients - clients_prev_week, 0))
    t_active, t_active_up = _trend(active_clients, clients_prev_week)
    t_tickets, t_tickets_up = _trend(open_tickets, tickets_prev_week)
    t_ship, t_ship_up = _trend(active_shipments, max(active_shipments - 3, 0))
    t_docs, t_docs_up = _trend(recent_documents, docs_prev_week)
    t_issues, t_issues_up = _trend(pending_issues, max(pending_issues - 2, 0))

    metrics = [
        EmployeeMetricCard(key="total_clients", value=total_clients, label="Total Clients", trend=t_total, trend_up=t_total_up, icon="users"),
        EmployeeMetricCard(key="active_clients", value=active_clients, label="Active Clients", trend=t_active, trend_up=t_active_up, icon="users"),
        EmployeeMetricCard(key="open_tickets", value=open_tickets, label="Open Tickets", trend=t_tickets, trend_up=not t_tickets_up, icon="ticket"),
        EmployeeMetricCard(key="active_shipments", value=active_shipments, label="Active Shipments", trend=t_ship, trend_up=t_ship_up, icon="package"),
        EmployeeMetricCard(key="recent_documents", value=recent_documents, label="Recent Documents", trend=t_docs, trend_up=t_docs_up, icon="file"),
        EmployeeMetricCard(key="pending_issues", value=pending_issues, label="Pending Issues", trend=t_issues, trend_up=not t_issues_up, icon="alert"),
    ]

    return EmployeeClientOpsStats(
        total_clients=total_clients,
        active_clients=active_clients,
        open_tickets=open_tickets,
        active_shipments=active_shipments,
        recent_documents=recent_documents,
        pending_issues=pending_issues,
        metrics=metrics,
    )


@router.get("/clients", response_model=EmployeeClientListResponse)
def list_clients(
    q: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status"),
    activity: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=100),
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeClientListResponse:
    stmt = select(User).where(User.role == UserRole.client.value)
    if q:
        like = f"%{q.strip().lower()}%"
        extra_ids: set[int] = set()
        extra_ids.update(
            db.scalars(
                select(TrackingRequest.user_id).where(func.lower(TrackingRequest.tracking_number).like(like))
            ).all()
        )
        extra_ids.update(
            db.scalars(
                select(SupportTicket.user_id).where(
                    or_(
                        func.lower(SupportTicket.subject).like(like),
                        func.lower(SupportTicket.ticket_number).like(like),
                    )
                )
            ).all()
        )
        extra_ids.update(
            db.scalars(
                select(ReportRun.generated_by_user_id).where(
                    ReportRun.generated_by_user_id.isnot(None),
                    func.lower(ReportRun.name).like(like),
                )
            ).all()
        )
        conditions = [func.lower(User.full_name).like(like), func.lower(User.email).like(like)]
        if extra_ids:
            conditions.append(User.id.in_(extra_ids))
        stmt = stmt.where(or_(*conditions))
    if status_filter and status_filter != "all":
        stmt = stmt.where(User.status == status_filter)
    rows = list(db.scalars(stmt.order_by(User.created_at.desc())).all())
    items = [_client_summary(db, u) for u in rows]
    if activity == "recent":
        items.sort(key=lambda x: x.recent_trackings, reverse=True)
    total = len(items)
    total_pages = max(1, (total + limit - 1) // limit)
    safe_page = min(page, total_pages)
    offset = (safe_page - 1) * limit
    page_items = items[offset : offset + limit]
    return EmployeeClientListResponse(
        items=page_items,
        total=total,
        page=safe_page,
        limit=limit,
        total_pages=total_pages,
    )


def _client_detail_payload(db: Session, user: User) -> EmployeeClientDetail:
    summary = _client_summary(db, user)
    resolved_tickets = int(
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.user_id == user.id, SupportTicket.status == "resolved")
        )
        or 0
    )
    return EmployeeClientDetail(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        status=user.status,
        preferred_language=user.preferred_language,
        organization_id=user.organization_id,
        created_at=user.created_at,
        open_tickets=summary.open_tickets,
        total_trackings=summary.recent_trackings,
        total_documents=summary.documents_count,
        company=summary.company,
        avatar_initials=summary.avatar_initials,
        last_login=_client_last_login(db, user.id),
        last_activity=summary.last_activity,
        pending_issues=summary.pending_issues,
        active_shipments=summary.active_shipments,
        assigned_employee=_client_assigned_employee(db, user.id),
        resolved_tickets=resolved_tickets,
    )


@router.get("/clients/{client_id}", response_model=EmployeeClientDetail)
def get_client_detail(
    client_id: int,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeClientDetail:
    user = db.get(User, client_id)
    if user is None or user.role != UserRole.client.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable.")
    return _client_detail_payload(db, user)


@router.get("/clients/{client_id}/activity", response_model=list[EmployeeClientActivityEvent])
def client_activity(
    client_id: int,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeClientActivityEvent]:
    user = db.get(User, client_id)
    if user is None or user.role != UserRole.client.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable.")
    return _client_activity_events(db, client_id)


@router.get("/clients/{client_id}/documents", response_model=list[EmployeeDocumentItem])
def client_documents(
    client_id: int,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeDocumentItem]:
    user = db.get(User, client_id)
    if user is None or user.role != UserRole.client.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable.")
    items: list[EmployeeDocumentItem] = []
    reports = list(
        db.scalars(
            select(ReportRun)
            .where(ReportRun.generated_by_user_id == client_id)
            .order_by(ReportRun.created_at.desc())
            .limit(50)
        ).all()
    )
    for r in reports:
        dtype = "report" if r.format in ("pdf", "xlsx") else "export"
        items.append(
            EmployeeDocumentItem(
                id=f"report-{r.id}",
                title=r.name,
                doc_type=dtype,
                tracking_number="",
                client_name=user.full_name,
                client_id=client_id,
                created_at=r.created_at,
            )
        )
    trackings = list(
        db.scalars(
            select(TrackingRequest)
            .where(TrackingRequest.user_id == client_id)
            .order_by(TrackingRequest.created_at.desc())
            .limit(40)
        ).all()
    )
    seen_tracking: set[str] = set()
    for t in trackings:
        if t.tracking_number in seen_tracking:
            continue
        seen_tracking.add(t.tracking_number)
        st = (t.status or "").lower()
        if st in ("delivered", "livré"):
            dtype = "proof"
        elif "invoice" in st:
            dtype = "invoice"
        else:
            dtype = "tracking"
        items.append(
            EmployeeDocumentItem(
                id=f"tracking-{t.id}",
                title=f"POD / Tracking {t.tracking_number}",
                doc_type=dtype,
                tracking_number=t.tracking_number,
                client_name=user.full_name,
                client_id=client_id,
                created_at=t.created_at,
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items


@router.get("/clients/{client_id}/notifications", response_model=EmployeeNotificationListResponse)
def client_notifications(
    client_id: int,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeNotificationListResponse:
    user = db.get(User, client_id)
    if user is None or user.role != UserRole.client.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable.")
    rows = list(
        db.scalars(
            select(ClientNotification)
            .where(ClientNotification.user_id == client_id)
            .order_by(ClientNotification.created_at.desc())
            .limit(80)
        ).all()
    )
    unread = sum(1 for n in rows if not n.is_read)
    items = [EmployeeNotificationRead.model_validate(employee_notification_to_dict(n)) for n in rows]
    return EmployeeNotificationListResponse(items=items, unread_count=unread, total=len(items), page=1, limit=len(items) or 20, total_pages=1)


@router.get("/clients/{client_id}/trackings", response_model=list[EmployeeTrackingItem])
def client_trackings(
    client_id: int,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeTrackingItem]:
    user = db.get(User, client_id)
    if user is None or user.role != UserRole.client.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable.")
    rows = list(
        db.scalars(
            select(TrackingRequest)
            .where(TrackingRequest.user_id == client_id)
            .order_by(TrackingRequest.created_at.desc())
            .limit(100)
        ).all()
    )
    return [
        EmployeeTrackingItem(
            id=r.id,
            tracking_number=r.tracking_number,
            status=r.status or "",
            current_location=r.current_location or "",
            estimated_delivery=r.estimated_delivery or "",
            user_question=r.user_question or "",
            created_at=r.created_at,
            client_name=user.full_name,
            client_id=user.id,
        )
        for r in rows
    ]


@router.get("/clients/{client_id}/shipments", response_model=list[EmployeeTrackingItem])
def client_shipments(
    client_id: int,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeTrackingItem]:
    return client_trackings(client_id, employee, db)


@router.get("/clients/{client_id}/tickets", response_model=SupportTicketListResponse)
def client_tickets(
    client_id: int,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> SupportTicketListResponse:
    user = db.get(User, client_id)
    if user is None or user.role != UserRole.client.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable.")
    rows = list(
        db.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == client_id)
            .order_by(SupportTicket.created_at.desc())
        ).all()
    )
    return SupportTicketListResponse(items=[_ticket_to_read(t) for t in rows])


@router.get("/tracking/stats", response_model=EmployeeTrackingOpsStats)
def tracking_ops_stats(
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeTrackingOpsStats:
    all_trackings = list(db.scalars(select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(300)).all())
    total = int(db.scalar(select(func.count()).select_from(TrackingRequest)) or 0)
    exception_count = sum(1 for t in all_trackings if _is_tracking_exception(t.status))
    delayed_count = sum(1 for t in all_trackings if _is_tracking_delayed(t.status))
    active = sum(
        1
        for t in all_trackings
        if (t.status or "").lower() not in ("delivered", "livré", "cancelled", "annulé")
    )
    t_active, t_active_up = _trend(active, max(active - 2, 0))
    t_exc, t_exc_up = _trend(exception_count, max(exception_count - 1, 0))
    t_delay, t_delay_up = _trend(delayed_count, max(delayed_count - 1, 0))
    t_total, t_total_up = _trend(total, max(total - 5, 0))
    metrics = [
        EmployeeMetricCard(key="active", value=active, label="Active Shipments", trend=t_active, trend_up=t_active_up, icon="package"),
        EmployeeMetricCard(key="exceptions", value=exception_count, label="Exceptions", trend=t_exc, trend_up=not t_exc_up, icon="alert"),
        EmployeeMetricCard(key="delayed", value=delayed_count, label="Delayed", trend=t_delay, trend_up=not t_delay_up, icon="clock"),
        EmployeeMetricCard(key="total", value=total, label="Total Trackings", trend=t_total, trend_up=t_total_up, icon="package"),
    ]
    return EmployeeTrackingOpsStats(
        active_shipments=active,
        delayed_count=delayed_count,
        exception_count=exception_count,
        total_trackings=total,
        metrics=metrics,
    )


@router.get("/tracking", response_model=list[EmployeeTrackingItem])
def search_tracking(
    q: str | None = Query(default=None, max_length=120),
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeTrackingItem]:
    stmt = select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(80)
    if q:
        like = f"%{q.strip().lower()}%"
        matching_users = list(
            db.scalars(
                select(User.id).where(
                    User.role == UserRole.client.value,
                    or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)),
                )
            ).all()
        )
        conditions = [func.lower(TrackingRequest.tracking_number).like(like)]
        if matching_users:
            conditions.append(TrackingRequest.user_id.in_(matching_users))
        stmt = stmt.where(or_(*conditions))
    rows = list(db.scalars(stmt).all())
    user_ids = {r.user_id for r in rows}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    return [_tracking_item_from_row(r, users) for r in rows]


@router.get("/tracking/{tracking_number}", response_model=EmployeeShipmentDetail)
def get_shipment_detail(
    tracking_number: str,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeShipmentDetail:
    detail = _build_shipment_detail(db, tracking_number)
    write_log(
        db,
        action="employee.tracking_lookup",
        message=f"Consultation shipment {detail.tracking_number}",
        category="system",
        level="INFO",
        actor_user_id=employee.id,
        ip_address=client_ip(request),
        metadata={"tracking_number": detail.tracking_number},
    )
    db.commit()
    return detail


@router.get("/tracking/{tracking_number}/live", response_model=EmployeeShipmentDetail)
def live_tracking(
    tracking_number: str,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeShipmentDetail:
    """Legacy alias — returns structured shipment detail, never raw JSON."""
    return get_shipment_detail(tracking_number, request, employee, db)


def _list_shipments_query(
    db: Session,
    q: str | None = None,
    status_filter: str | None = None,
    client_filter: str | None = None,
):
    stmt = select(TrackingRequest).order_by(TrackingRequest.created_at.desc())
    if q:
        like = f"%{q.strip().lower()}%"
        matching_users = list(
            db.scalars(
                select(User.id).where(
                    User.role == UserRole.client.value,
                    or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)),
                )
            ).all()
        )
        conditions = [func.lower(TrackingRequest.tracking_number).like(like)]
        if matching_users:
            conditions.append(TrackingRequest.user_id.in_(matching_users))
        stmt = stmt.where(or_(*conditions))
    if client_filter:
        like = f"%{client_filter.strip().lower()}%"
        matching_users = list(
            db.scalars(
                select(User.id).where(
                    User.role == UserRole.client.value,
                    or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)),
                )
            ).all()
        )
        if matching_users:
            stmt = stmt.where(TrackingRequest.user_id.in_(matching_users))
        else:
            stmt = stmt.where(TrackingRequest.id == -1)
    if status_filter and status_filter != "all":
        sf = status_filter.lower()
        if sf == "active":
            stmt = stmt.where(
                ~func.lower(TrackingRequest.status).in_(("delivered", "livré", "cancelled", "annulé"))
            )
        elif sf == "exception":
            rows_all = list(db.scalars(stmt).all())
            exc_ids = [r.id for r in rows_all if _is_tracking_exception(r.status)]
            stmt = select(TrackingRequest).where(TrackingRequest.id.in_(exc_ids) if exc_ids else TrackingRequest.id == -1)
        elif sf == "delayed":
            rows_all = list(db.scalars(stmt).all())
            delay_ids = [r.id for r in rows_all if _is_tracking_delayed(r.status)]
            stmt = select(TrackingRequest).where(TrackingRequest.id.in_(delay_ids) if delay_ids else TrackingRequest.id == -1)
        elif sf == "delivered":
            stmt = stmt.where(func.lower(TrackingRequest.status).in_(("delivered", "livré")))
    return stmt


@router.get("/shipments", response_model=EmployeeShipmentListResponse)
def list_shipments(
    tracking: str | None = Query(default=None, max_length=120),
    client: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=100),
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeShipmentListResponse:
    search_q = q or tracking
    stmt = _list_shipments_query(db, search_q, status_filter, client)
    rows = list(db.scalars(stmt).all())
    user_ids = {r.user_id for r in rows}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    items = [_tracking_item_from_row(r, users) for r in rows]
    total = len(items)
    total_pages = max(1, (total + limit - 1) // limit)
    safe_page = min(page, total_pages)
    offset = (safe_page - 1) * limit
    return EmployeeShipmentListResponse(
        items=items[offset : offset + limit],
        total=total,
        page=safe_page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/shipments/{tracking_number}", response_model=EmployeeShipmentDetail)
def get_shipment_by_number(
    tracking_number: str,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeShipmentDetail:
    return get_shipment_detail(tracking_number, request, employee, db)


def _pdf_safe_text(value: str | None) -> str:
    """Helvetica (latin-1) cannot render arbitrary Unicode from FedEx / client data."""
    if not value:
        return ""
    text = str(value)
    for src, dst in (
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2026", "..."),
        ("\u00a0", " "),
    ):
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _shipment_export_pdf_bytes(detail: EmployeeShipmentDetail) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, _pdf_safe_text(f"Shipment Export - {detail.tracking_number}"), ln=True)
    pdf.ln(4)
    for label, val in [
        ("Status", detail.status),
        ("Location", detail.current_location),
        ("ETA", detail.estimated_delivery),
        ("Recipient", detail.recipient),
        ("Client", detail.client_name),
        ("Service", detail.service_type),
    ]:
        pdf.cell(0, 8, _pdf_safe_text(f"{label}: {val}"), ln=True)
    pdf.ln(4)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(0, 8, "Timeline", ln=True)
    pdf.set_font("Helvetica", size=10)
    for ev in detail.timeline[:20]:
        line = f"{ev.date} {ev.time} - {ev.description} ({ev.location})"
        pdf.multi_cell(0, 6, _pdf_safe_text(line))
    return pdf.output()


@router.get("/shipments/{tracking_number}/export")
def export_shipment(
    tracking_number: str,
    format: str = Query(default="pdf", pattern="^(pdf|txt)$"),
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    detail = _build_shipment_detail(db, tracking_number)
    if format == "txt":
        lines = [
            f"Tracking: {detail.tracking_number}",
            f"Status: {detail.status}",
            f"Location: {detail.current_location}",
            f"ETA: {detail.estimated_delivery}",
            f"Recipient: {detail.recipient}",
            f"Client: {detail.client_name}",
            "",
            "Timeline:",
        ]
        for ev in detail.timeline:
            lines.append(f"{ev.date} {ev.time} — {ev.description} ({ev.location})")
        content = "\n".join(lines).encode("utf-8")
        return StreamingResponse(
            iter([content]),
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="shipment-{detail.tracking_number}.txt"'},
        )
    pdf_bytes = _shipment_export_pdf_bytes(detail)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="shipment-{detail.tracking_number}.pdf"'},
    )


@router.get("/shipments/{tracking_number}/pod")
def download_shipment_pod(
    tracking_number: str,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    detail = _build_shipment_detail(db, tracking_number)
    if not detail.pod_available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La preuve de livraison est disponible une fois le colis livré.",
        )
    try:
        pdf_bytes = get_proof_of_delivery_pdf(detail.tracking_number)
    except fedex_service.TrackingLookupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    write_log(
        db,
        action="employee.shipment_pod",
        message=f"POD téléchargé — {detail.tracking_number}",
        category="system",
        level="INFO",
        actor_user_id=employee.id,
        ip_address=client_ip(request),
        metadata={"tracking_number": detail.tracking_number},
        commit=True,
    )
    filename = f"POD-{detail.tracking_number}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/documents", response_model=list[EmployeeDocumentItem])
def list_documents(
    q: str | None = Query(default=None),
    doc_type: str | None = Query(default=None, alias="type"),
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeDocumentItem]:
    items: list[EmployeeDocumentItem] = []
    report_stmt = select(ReportRun).order_by(ReportRun.created_at.desc()).limit(100)
    if q:
        report_stmt = report_stmt.where(func.lower(ReportRun.name).like(f"%{q.strip().lower()}%"))
    reports = list(db.scalars(report_stmt).all())
    user_ids = {r.generated_by_user_id for r in reports if r.generated_by_user_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    for r in reports:
        uid = r.generated_by_user_id or 0
        u = users.get(uid)
        dtype = "report" if r.format in ("pdf", "xlsx") else "export"
        if doc_type and doc_type != "all" and dtype != doc_type:
            continue
        items.append(
            EmployeeDocumentItem(
                id=f"report-{r.id}",
                title=r.name,
                doc_type=dtype,
                tracking_number="",
                client_name=u.full_name if u else "—",
                client_id=uid,
                created_at=r.created_at,
            )
        )
    tr_stmt = select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(80)
    if q:
        tr_stmt = tr_stmt.where(func.lower(TrackingRequest.tracking_number).like(f"%{q.strip().lower()}%"))
    trackings = list(db.scalars(tr_stmt).all())
    tr_user_ids = {t.user_id for t in trackings}
    tr_users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(tr_user_ids))).all()} if tr_user_ids else {}
    for t in trackings:
        if doc_type and doc_type not in ("all", "proof", "tracking"):
            continue
        u = tr_users.get(t.user_id)
        items.append(
            EmployeeDocumentItem(
                id=f"tracking-{t.id}",
                title=f"POD / Tracking {t.tracking_number}",
                doc_type="proof" if (t.status or "").lower() in ("delivered", "livré") else "tracking",
                tracking_number=t.tracking_number,
                client_name=u.full_name if u else "—",
                client_id=t.user_id,
                created_at=t.created_at,
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:100]


@router.get("/documents/{doc_id}/download")
def download_document(
    doc_id: str,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
):
    if doc_id.startswith("report-"):
        try:
            run_id = int(doc_id.replace("report-", ""))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable.") from exc
        try:
            run, path = get_run_file(db, run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable.") from exc
        media = {
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "json": "application/json",
            "pdf": "application/pdf",
        }
        write_log(
            db,
            action="employee.document_download",
            message=f"Rapport téléchargé — {run.name}",
            category="system",
            level="INFO",
            actor_user_id=employee.id,
            ip_address=client_ip(request),
            metadata={"doc_id": doc_id, "run_id": run_id},
            commit=True,
        )
        return FileResponse(
            path,
            media_type=media.get(run.format, "application/octet-stream"),
            filename=path.name,
        )
    if doc_id.startswith("tracking-"):
        try:
            tracking_id = int(doc_id.replace("tracking-", ""))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable.") from exc
        row = db.get(TrackingRequest, tracking_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suivi introuvable.")
        detail = _build_shipment_detail(db, row.tracking_number)
        if detail.pod_available:
            try:
                pdf_bytes = get_proof_of_delivery_pdf(detail.tracking_number)
            except fedex_service.TrackingLookupError:
                pdf_bytes = _shipment_export_pdf_bytes(detail)
                filename = f"shipment-{detail.tracking_number}.pdf"
            else:
                filename = f"POD-{detail.tracking_number}.pdf"
        else:
            pdf_bytes = _shipment_export_pdf_bytes(detail)
            filename = f"shipment-{detail.tracking_number}.pdf"
        write_log(
            db,
            action="employee.document_download",
            message=f"Document téléchargé — {detail.tracking_number}",
            category="system",
            level="INFO",
            actor_user_id=employee.id,
            ip_address=client_ip(request),
            metadata={"doc_id": doc_id, "tracking_number": detail.tracking_number},
            commit=True,
        )
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable.")


# ── Support tickets (helpdesk) ───────────────────────────────────────────────

def _ticket_tracking_number(ticket: SupportTicket, db: Session) -> str:
    for text in (ticket.subject, ticket.message):
        tn = llm_service.extract_tracking_number(text or "")
        if tn:
            return tn
    for msg in ticket.messages or []:
        tn = llm_service.extract_tracking_number(msg.body or "")
        if tn:
            return tn
    if (ticket.category or "") == "tracking" and ticket.user_id:
        latest = db.scalar(
            select(TrackingRequest.tracking_number)
            .where(TrackingRequest.user_id == ticket.user_id)
            .order_by(TrackingRequest.created_at.desc())
            .limit(1)
        )
        if latest:
            return latest
    return ""


def _ticket_last_activity(ticket: SupportTicket) -> tuple[str, datetime]:
    msgs = ticket.messages or []
    if msgs:
        last = msgs[-1]
        return (last.body or "")[:160], last.created_at
    return (ticket.message or "")[:160], ticket.created_at


def _ticket_unread(ticket: SupportTicket) -> bool:
    if ticket.status in ("resolved", "closed"):
        return False
    msgs = ticket.messages or []
    if not msgs:
        return True
    return msgs[-1].author_role == "user"


def _ticket_assigned_employee(ticket: SupportTicket) -> tuple[str, int | None]:
    for msg in reversed(ticket.messages or []):
        if msg.author_role in ("employe", "admin", "employee") and msg.author_user_id:
            name = msg.author.full_name if msg.author else "Support"
            return name or "Support", msg.author_user_id
    return "", None


def _helpdesk_message_to_read(row: SupportTicketMessage) -> EmployeeHelpdeskMessageRead:
    author_name = None
    is_internal = row.author_role == "internal"
    if row.author:
        if row.author_role == "admin":
            author_name = row.author.full_name or "Admin"
        elif row.author_role in ("employe", "employee"):
            author_name = row.author.full_name or "Support"
        elif row.author_role == "user":
            author_name = row.author.full_name or "Client"
        elif row.author_role == "internal":
            author_name = row.author.full_name or "Support"
    return EmployeeHelpdeskMessageRead(
        id=row.id,
        author_role=row.author_role,
        body=row.body,
        attachment_url=row.attachment_url,
        created_at=row.created_at,
        author_name=author_name,
        is_internal=is_internal,
    )


def _helpdesk_ticket_summary(ticket: SupportTicket, db: Session) -> EmployeeHelpdeskTicketSummary:
    user = ticket.user
    last_activity, last_at = _ticket_last_activity(ticket)
    assigned_name, assigned_id = _ticket_assigned_employee(ticket)
    return EmployeeHelpdeskTicketSummary(
        id=ticket.id,
        ticket_number=ticket.ticket_number or generate_ticket_number(ticket.id),
        subject=ticket.subject,
        category=ticket.category or "other",
        priority=ticket.priority or "medium",
        status=ticket.status,
        customer_name=user.full_name if user else "Client",
        customer_email=user.email if user else "",
        client_id=ticket.user_id,
        last_activity=last_activity,
        last_activity_at=last_at,
        unread=_ticket_unread(ticket),
        tracking_number=_ticket_tracking_number(ticket, db),
        assigned_employee=assigned_name,
        assigned_employee_id=assigned_id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _count_unread_helpdesk_tickets(db: Session) -> int:
    rows = list(
        db.scalars(
            select(SupportTicket)
            .options(joinedload(SupportTicket.messages))
            .where(SupportTicket.status.notin_(("resolved", "closed")))
            .limit(300)
        )
        .unique()
        .all()
    )
    return sum(1 for t in rows if _ticket_unread(t))


def _helpdesk_stats(db: Session) -> EmployeeHelpdeskStats:
    open_c = int(db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "open")) or 0)
    pending_c = int(db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "pending")) or 0)
    resolved_c = int(db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "resolved")) or 0)
    closed_c = int(db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "closed")) or 0)
    escalated_c = int(db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "escalated")) or 0)
    unread = _count_unread_helpdesk_tickets(db)
    return EmployeeHelpdeskStats(
        open=open_c,
        pending=pending_c,
        resolved=resolved_c,
        closed=closed_c,
        escalated=escalated_c,
        unread=unread,
        total_active=open_c + pending_c + escalated_c,
    )


@router.get("/support/helpdesk/stats", response_model=EmployeeHelpdeskStats)
def helpdesk_stats(
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeHelpdeskStats:
    return _helpdesk_stats(db)


@router.get("/support/employees", response_model=list[EmployeeHelpdeskEmployeeOption])
def list_helpdesk_employees(
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeHelpdeskEmployeeOption]:
    rows = list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.employe.value, User.status == UserStatus.active.value)
            .order_by(User.full_name.asc())
        ).all()
    )
    return [
        EmployeeHelpdeskEmployeeOption(id=u.id, full_name=u.full_name or u.email, email=u.email)
        for u in rows
    ]


@router.get("/support/tickets", response_model=EmployeeHelpdeskTicketListResponse)
def list_support_tickets(
    status_filter: str = Query(default="all", alias="status"),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    assigned: int | None = Query(default=None),
    q: str | None = Query(default=None),
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeHelpdeskTicketListResponse:
    stmt = (
        select(SupportTicket)
        .options(joinedload(SupportTicket.user))
        .options(joinedload(SupportTicket.messages).joinedload(SupportTicketMessage.author))
        .order_by(SupportTicket.updated_at.desc(), SupportTicket.created_at.desc())
        .limit(200)
    )
    if status_filter != "all":
        stmt = stmt.where(SupportTicket.status == status_filter)
    if priority:
        stmt = stmt.where(SupportTicket.priority == priority)
    if category:
        stmt = stmt.where(SupportTicket.category == category)
    if q:
        needle = q.strip().lower()
        like = f"%{needle}%"
        user_ids = list(
            db.scalars(
                select(User.id).where(
                    or_(
                        func.lower(User.full_name).like(like),
                        func.lower(User.email).like(like),
                    )
                )
            ).all()
        )
        tracking_ids: list[int] = []
        if needle:
            tracking_user_ids = list(
                db.scalars(
                    select(TrackingRequest.user_id).where(
                        func.lower(TrackingRequest.tracking_number).like(like)
                    )
                ).all()
            )
            if tracking_user_ids:
                tracking_ids = list(
                    db.scalars(
                        select(SupportTicket.id).where(SupportTicket.user_id.in_(tracking_user_ids))
                    ).all()
                )
        conditions = [
            func.lower(SupportTicket.subject).like(like),
            func.lower(SupportTicket.message).like(like),
            func.lower(SupportTicket.ticket_number).like(like),
            cast(SupportTicket.id, String).like(like),
        ]
        if user_ids:
            conditions.append(SupportTicket.user_id.in_(user_ids))
        if tracking_ids:
            conditions.append(SupportTicket.id.in_(tracking_ids))
        stmt = stmt.where(or_(*conditions))
    rows = list(db.scalars(stmt).unique().all())
    items = [_helpdesk_ticket_summary(t, db) for t in rows]
    if assigned is not None:
        items = [i for i in items if i.assigned_employee_id == assigned]
    return EmployeeHelpdeskTicketListResponse(items=items, total=len(items))


@router.get("/support/tickets/{ticket_id}", response_model=EmployeeHelpdeskTicketDetail)
def get_support_ticket(
    ticket_id: int,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeHelpdeskTicketDetail:
    ticket = db.scalars(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages).joinedload(SupportTicketMessage.author))
        .options(joinedload(SupportTicket.user))
        .where(SupportTicket.id == ticket_id)
    ).unique().one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    user = ticket.user
    assigned_name, assigned_id = _ticket_assigned_employee(ticket)
    return EmployeeHelpdeskTicketDetail(
        id=ticket.id,
        ticket_number=ticket.ticket_number or generate_ticket_number(ticket.id),
        subject=ticket.subject,
        message=ticket.message,
        category=ticket.category or "other",
        priority=ticket.priority or "medium",
        status=ticket.status,
        attachment_url=ticket.attachment_url,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        customer_name=user.full_name if user else "Client",
        customer_email=user.email if user else "",
        client_id=ticket.user_id,
        tracking_number=_ticket_tracking_number(ticket, db),
        assigned_employee=assigned_name,
        assigned_employee_id=assigned_id,
        messages=[_helpdesk_message_to_read(m) for m in ticket.messages],
    )


@router.post("/support/tickets/{ticket_id}/reply", response_model=EmployeeHelpdeskMessageRead)
def reply_support_ticket(
    ticket_id: int,
    payload: SupportMessageCreate,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeHelpdeskMessageRead:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    body = _sanitize_text(payload.message)
    if not _message_allowed(body, payload.attachmentUrl):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message or attachment required.")
    row = SupportTicketMessage(
        ticket_id=ticket.id,
        author_role="employe",
        author_user_id=employee.id,
        body=body,
        attachment_url=payload.attachmentUrl,
    )
    db.add(row)
    ticket.admin_note = body[:500]
    if ticket.status == SupportTicketStatus.open:
        ticket.status = SupportTicketStatus.pending
    create_user_notification(
        db,
        user_id=ticket.user_id,
        type="admin_reply",
        title="Réponse du support",
        message=body[:500],
        sender_id=employee.id,
        sender_role="employe",
        priority=ticket.priority or "medium",
        related_ticket_id=ticket.id,
        link=f"/notifications?ticket={ticket.id}",
    )
    write_log(
        db,
        action="support.employee_reply",
        message=f"Réponse employé sur ticket #{ticket.id}",
        category="system",
        level="INFO",
        user_id=ticket.user_id,
        actor_user_id=employee.id,
        ip_address=client_ip(request),
        metadata={"ticket_id": ticket.id},
        commit=False,
    )
    db.commit()
    db.refresh(row)
    row = db.scalar(
        select(SupportTicketMessage)
        .options(joinedload(SupportTicketMessage.author))
        .where(SupportTicketMessage.id == row.id)
    )
    assert row is not None
    return _helpdesk_message_to_read(row)


@router.patch("/support/tickets/{ticket_id}/status", response_model=SupportTicketRead)
def update_ticket_status(
    ticket_id: int,
    payload: SupportTicketStatusUpdate,
    _: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> SupportTicketRead:
    allowed = {"open", "pending", "resolved", "closed", "escalated"}
    if payload.status not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Statut invalide.")
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    ticket.status = payload.status
    if payload.status == "escalated":
        key = f"support-escalated-{ticket.id}"
        exists = db.scalar(select(PlatformNotification.id).where(PlatformNotification.external_key == key))
        if not exists:
            db.add(
                PlatformNotification(
                    external_key=key,
                    category="incidents",
                    title="Ticket escaladé",
                    message=f"Ticket #{ticket.id} — {ticket.subject}",
                    route=f"/admin?section=notifications&ticket={ticket.id}",
                    priority="high",
                    channel="web",
                    icon="alert-triangle",
                    action_label="Voir",
                    action_type="support_ticket",
                    action_ref=str(ticket.id),
                )
            )
    db.commit()
    db.refresh(ticket)
    return _ticket_to_read(ticket)


@router.post("/support/tickets/{ticket_id}/internal-note", response_model=EmployeeHelpdeskMessageRead)
def add_internal_note(
    ticket_id: int,
    payload: EmployeeHelpdeskInternalNote,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeHelpdeskMessageRead:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    body = _sanitize_text(payload.message)
    if not _message_allowed(body, payload.attachmentUrl):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message or attachment required.")
    row = SupportTicketMessage(
        ticket_id=ticket.id,
        author_role="internal",
        author_user_id=employee.id,
        body=body,
        attachment_url=payload.attachmentUrl,
    )
    db.add(row)
    write_log(
        db,
        action="support.internal_note",
        message=f"Note interne sur ticket #{ticket.id}",
        category="system",
        level="INFO",
        user_id=ticket.user_id,
        actor_user_id=employee.id,
        ip_address=client_ip(request),
        metadata={"ticket_id": ticket.id},
        commit=False,
    )
    db.commit()
    db.refresh(row)
    row = db.scalar(
        select(SupportTicketMessage)
        .options(joinedload(SupportTicketMessage.author))
        .where(SupportTicketMessage.id == row.id)
    )
    assert row is not None
    return _helpdesk_message_to_read(row)


@router.patch("/support/tickets/{ticket_id}/assign", response_model=EmployeeHelpdeskTicketDetail)
def assign_support_ticket(
    ticket_id: int,
    payload: EmployeeHelpdeskAssign,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeHelpdeskTicketDetail:
    ticket = db.scalars(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages).joinedload(SupportTicketMessage.author))
        .options(joinedload(SupportTicket.user))
        .where(SupportTicket.id == ticket_id)
    ).unique().one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    target_id = payload.employee_id or employee.id
    target = db.get(User, target_id)
    if target is None or target.role != UserRole.employe.value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Employé invalide.")
    assignee_name = target.full_name or target.email
    db.add(
        SupportTicketMessage(
            ticket_id=ticket.id,
            author_role="internal",
            author_user_id=employee.id,
            body=f"Ticket assigné à {assignee_name}.",
        )
    )
    if ticket.status == SupportTicketStatus.open:
        ticket.status = SupportTicketStatus.pending
    write_log(
        db,
        action="support.assign",
        message=f"Ticket #{ticket.id} assigné à {assignee_name}",
        category="system",
        level="INFO",
        user_id=ticket.user_id,
        actor_user_id=employee.id,
        ip_address=client_ip(request),
        metadata={"ticket_id": ticket.id, "assignee_id": target_id},
        commit=False,
    )
    db.commit()
    db.refresh(ticket)
    user = ticket.user
    assigned_name, assigned_id = _ticket_assigned_employee(ticket)
    return EmployeeHelpdeskTicketDetail(
        id=ticket.id,
        ticket_number=ticket.ticket_number or generate_ticket_number(ticket.id),
        subject=ticket.subject,
        message=ticket.message,
        category=ticket.category or "other",
        priority=ticket.priority or "medium",
        status=ticket.status,
        attachment_url=ticket.attachment_url,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        customer_name=user.full_name if user else "Client",
        customer_email=user.email if user else "",
        client_id=ticket.user_id,
        tracking_number=_ticket_tracking_number(ticket, db),
        assigned_employee=assigned_name,
        assigned_employee_id=assigned_id,
        messages=[_helpdesk_message_to_read(m) for m in ticket.messages],
    )


# ── Admin chat ───────────────────────────────────────────────────────────────

_ADMIN_CHAT_CHANNELS: list[dict[str, str]] = [
    {"id": "administrator", "name": "Administrator", "role": "Admin", "initial": "A"},
]


def _attachment_name(url: str | None) -> str:
    if not url:
        return ""
    return url.rsplit("/", 1)[-1].split("?")[0] or "attachment"


def _mime_from_filename(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".xlsx", ".xls")):
        return "application/vnd.ms-excel"
    if lower.endswith(".csv"):
        return "text/csv"
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return "image/*"
    return "application/octet-stream"


def _admin_chat_rows(db: Session, employee_id: int) -> list[EmployeeAdminMessage]:
    return list(
        db.scalars(
            select(EmployeeAdminMessage)
            .where(EmployeeAdminMessage.employee_id == employee_id)
            .order_by(EmployeeAdminMessage.created_at.asc())
            .limit(500)
        ).all()
    )


def _admin_chat_unread(rows: list[EmployeeAdminMessage]) -> int:
    return sum(1 for r in rows if r.sender_role == "admin" and not r.is_read)


async def _broadcast_admin_chat_message(employee_id: int, message: dict, unread_count: int) -> None:
    await employee_admin_chat_hub.notify_message(employee_id, message, unread_count)


def _admin_msg_read(row: EmployeeAdminMessage, db: Session) -> EmployeeAdminMessageRead:
    sender = db.get(User, row.sender_user_id)
    return EmployeeAdminMessageRead(
        id=row.id,
        sender_role=row.sender_role,
        sender_name=sender.full_name if sender else None,
        body=row.body,
        attachment_url=row.attachment_url,
        is_read=row.is_read,
        created_at=row.created_at,
    )


def _build_admin_chat_workspace(employee: User, db: Session) -> EmployeeAdminChatWorkspace:
    rows = _admin_chat_rows(db, employee.id)
    unread = _admin_chat_unread(rows)
    messages = [_admin_msg_read(r, db) for r in rows]
    last = rows[-1] if rows else None
    last_preview = (last.body or _attachment_name(last.attachment_url) or "")[:160] if last else ""
    last_at = last.created_at if last else None
    created_at = rows[0].created_at if rows else None

    conversations: list[EmployeeAdminChatConversation] = []
    for i, ch in enumerate(_ADMIN_CHAT_CHANNELS):
        conversations.append(
            EmployeeAdminChatConversation(
                id=ch["id"],
                name=ch["name"],
                role=ch["role"],
                avatar_initial=ch["initial"],
                online=True,
                last_message=last_preview,
                last_message_at=last_at,
                unread_count=unread if i == 0 else 0,
            )
        )

    participants: list[EmployeeAdminChatParticipant] = [
        EmployeeAdminChatParticipant(
            id=_ADMIN_CHAT_CHANNELS[0]["id"],
            name=_ADMIN_CHAT_CHANNELS[0]["name"],
            role=_ADMIN_CHAT_CHANNELS[0]["role"],
            avatar_initial=_ADMIN_CHAT_CHANNELS[0]["initial"],
            online=True,
        ),
    ]

    shared_files: list[EmployeeAdminChatSharedFile] = []
    for r in rows:
        if not r.attachment_url:
            continue
        sender = db.get(User, r.sender_user_id)
        fname = _attachment_name(r.attachment_url)
        shared_files.append(
            EmployeeAdminChatSharedFile(
                id=r.id,
                name=fname,
                url=r.attachment_url,
                mime_type=_mime_from_filename(fname),
                uploaded_at=r.created_at,
                uploaded_by=sender.full_name if sender else r.sender_role,
            )
        )

    return EmployeeAdminChatWorkspace(
        conversations=conversations,
        messages=messages,
        participants=participants,
        shared_files=shared_files,
        unread_count=unread,
        created_at=created_at,
        last_activity_at=last_at,
    )


@router.get("/admin-chat/workspace", response_model=EmployeeAdminChatWorkspace)
def get_admin_chat_workspace(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAdminChatWorkspace:
    return _build_admin_chat_workspace(employee, db)


@router.get("/admin-chat/search", response_model=EmployeeAdminChatSearchResponse)
def search_admin_chat(
    q: str = Query(min_length=1, max_length=120),
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAdminChatSearchResponse:
    needle = q.strip().lower()
    rows = _admin_chat_rows(db, employee.id)
    hits: list[EmployeeAdminChatSearchHit] = []

    for p in _ADMIN_CHAT_CHANNELS:
        blob = f"{p['name']} {p['role']}".lower()
        if needle in blob:
            hits.append(
                EmployeeAdminChatSearchHit(
                    kind="participant",
                    id=p["id"],
                    title=p["name"],
                    subtitle=p["role"],
                )
            )

    for r in rows:
        sender = db.get(User, r.sender_user_id)
        sender_name = (sender.full_name if sender else r.sender_role) or ""
        body = (r.body or "").lower()
        fname = _attachment_name(r.attachment_url).lower()
        if needle in body or needle in sender_name.lower() or (fname and needle in fname):
            hits.append(
                EmployeeAdminChatSearchHit(
                    kind="message" if needle in body else "file",
                    id=str(r.id),
                    title=(r.body or fname)[:120],
                    subtitle=sender_name,
                    message_id=r.id,
                )
            )
        elif r.attachment_url and needle in fname:
            hits.append(
                EmployeeAdminChatSearchHit(
                    kind="file",
                    id=f"file-{r.id}",
                    title=fname,
                    subtitle=sender_name,
                    message_id=r.id,
                )
            )

    return EmployeeAdminChatSearchResponse(query=q.strip(), items=hits[:40])


@router.post("/admin-chat/typing")
async def employee_admin_chat_typing(
    payload: EmployeeAdminChatTyping,
    employee: User = Depends(require_role(UserRole.employe.value)),
) -> dict[str, bool]:
    await employee_admin_chat_hub.set_typing(
        employee.id,
        sender_role="employe",
        sender_name=employee.full_name or "Employee",
        active=payload.active,
    )
    return {"ok": True}


@router.get("/admin-chat", response_model=EmployeeAdminChatResponse)
def get_admin_chat(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAdminChatResponse:
    rows = list(
        db.scalars(
            select(EmployeeAdminMessage)
            .where(EmployeeAdminMessage.employee_id == employee.id)
            .order_by(EmployeeAdminMessage.created_at.asc())
            .limit(500)
        ).all()
    )
    unread = sum(1 for r in rows if r.sender_role == "admin" and not r.is_read)
    return EmployeeAdminChatResponse(
        items=[_admin_msg_read(r, db) for r in rows],
        unread_count=unread,
    )


@router.post("/admin-chat/messages", response_model=EmployeeAdminMessageRead)
def post_admin_chat_message(
    payload: EmployeeAdminMessageCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAdminMessageRead:
    body = _HTML_TAG_RE.sub("", payload.body).strip()
    if not body and not payload.attachment_url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message requis.")
    row = EmployeeAdminMessage(
        employee_id=employee.id,
        sender_user_id=employee.id,
        sender_role="employe",
        body=body,
        attachment_url=payload.attachment_url,
        is_read=False,
    )
    db.add(row)
    _notify_admins_employee_message(db, employee, body)
    write_log(
        db,
        action="employee.admin_chat_send",
        message=f"Message admin-chat employé #{employee.id}",
        category="system",
        level="INFO",
        actor_user_id=employee.id,
        ip_address=client_ip(request),
        commit=False,
    )
    db.commit()
    db.refresh(row)
    read_row = _admin_msg_read(row, db)
    background_tasks.add_task(
        _broadcast_admin_chat_message,
        employee.id,
        read_row.model_dump(mode="json"),
        _admin_chat_unread(_admin_chat_rows(db, employee.id)),
    )
    return read_row


@router.patch("/admin-chat/read")
def mark_admin_chat_read(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    rows = list(
        db.scalars(
            select(EmployeeAdminMessage).where(
                EmployeeAdminMessage.employee_id == employee.id,
                EmployeeAdminMessage.sender_role == "admin",
                EmployeeAdminMessage.is_read.is_(False),
            )
        ).all()
    )
    for r in rows:
        r.is_read = True
    db.commit()
    return {"marked": len(rows)}


def _employee_notif_read(row: ClientNotification) -> EmployeeNotificationRead:
    return EmployeeNotificationRead.model_validate(employee_notification_to_dict(row))


def _employee_notif_filter_type(type_filter: str | None) -> set[str] | None:
    if not type_filter or type_filter in ("all", "all_types"):
        return None
    mapping = {
        "support": {"support_reply", "support_message", "admin_reply"},
        "tracking": {"tracking_update", "shipment_update"},
        "documents": {"document_uploaded", "document_ready", "export_ready"},
        "security": {"security_alert"},
        "admin": {"admin_message"},
        "system": {"system_alert"},
    }
    return mapping.get(type_filter)


# ── Notifications ────────────────────────────────────────────────────────────

@router.get("/notifications/stats", response_model=EmployeeNotificationStats)
def notifications_stats(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeNotificationStats:
    return EmployeeNotificationStats(**employee_notification_stats(db, employee.id))


@router.get("/notifications", response_model=EmployeeNotificationListResponse)
def list_notifications(
    search: str | None = Query(default=None, alias="search"),
    q: str | None = Query(default=None),
    type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeNotificationListResponse:
    term = (search or q or "").strip()
    stmt = select(ClientNotification).where(ClientNotification.user_id == employee.id)
    if status_filter == "unread":
        stmt = stmt.where(ClientNotification.is_read.is_(False))
    elif status_filter == "read":
        stmt = stmt.where(ClientNotification.is_read.is_(True))
    if term:
        like = f"%{term.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(ClientNotification.title).like(like),
                func.lower(ClientNotification.message).like(like),
                func.lower(ClientNotification.related_tracking_number).like(like),
            )
        )
    type_kinds = _employee_notif_filter_type(type)
    rows_all = list(db.scalars(stmt.order_by(ClientNotification.created_at.desc())).all())
    if type_kinds:
        rows_all = [
            r for r in rows_all if normalize_employee_type(r.kind, r.link) in type_kinds or r.kind in type_kinds
        ]
    total = len(rows_all)
    total_pages = max(1, (total + limit - 1) // limit)
    offset = (page - 1) * limit
    rows = rows_all[offset : offset + limit]
    unread = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == employee.id, ClientNotification.is_read.is_(False))
        )
        or 0
    )
    return EmployeeNotificationListResponse(
        items=[_employee_notif_read(r) for r in rows],
        unread_count=unread,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.patch("/notifications/read-all")
def mark_all_notifications_read(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> dict:
    rows = list(
        db.scalars(
            select(ClientNotification).where(
                ClientNotification.user_id == employee.id,
                ClientNotification.is_read.is_(False),
            )
        ).all()
    )
    now = _now()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return {"updated": len(rows)}


@router.patch("/notifications/{notif_id}/read", response_model=EmployeeNotificationRead)
def mark_notification_read(
    notif_id: int,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeNotificationRead:
    row = db.get(ClientNotification, notif_id)
    if row is None or row.user_id != employee.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable.")
    row.is_read = True
    row.read_at = _now()
    db.commit()
    db.refresh(row)
    return _employee_notif_read(row)


@router.delete("/notifications/{notif_id}")
def delete_notification(
    notif_id: int,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(ClientNotification, notif_id)
    if row is None or row.user_id != employee.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable.")
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.post("/notifications/test", response_model=EmployeeNotificationRead)
def create_test_notification(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeNotificationRead:
    from app.core.config import get_settings

    if not get_settings().debug:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dev only.")
    row = create_employee_notification(
        db,
        employee_id=employee.id,
        type="system_alert",
        title="Test notification",
        message="This is a test alert from the employee notifications API.",
        link="/employee/notifications",
    )
    db.commit()
    db.refresh(row)
    return _employee_notif_read(row)


# ── Settings ─────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=EmployeeSettingsRead)
def get_settings(
    employee: User = Depends(require_role(UserRole.employe.value)),
) -> EmployeeSettingsRead:
    return EmployeeSettingsRead(
        full_name=employee.full_name,
        email=employee.email,
        preferred_language=employee.preferred_language,
        response_preferences=employee.response_preferences or "",
    )


@router.patch("/settings", response_model=EmployeeSettingsRead)
def update_settings(
    payload: EmployeeSettingsUpdate,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeSettingsRead:
    if payload.full_name is not None:
        employee.full_name = payload.full_name.strip()[:255]
    if payload.preferred_language is not None:
        employee.preferred_language = payload.preferred_language.strip()[:8]
    if payload.response_preferences is not None:
        employee.response_preferences = payload.response_preferences[:4000]
    db.commit()
    db.refresh(employee)
    return EmployeeSettingsRead(
        full_name=employee.full_name,
        email=employee.email,
        preferred_language=employee.preferred_language,
        response_preferences=employee.response_preferences or "",
    )


# ── Employee AI Copilot ────────────────────────────────────────────────────────

_AI_STOP_WORDS = frozenset(
    {
        "le", "la", "les", "un", "une", "des", "de", "du", "find", "trouve", "trouver",
        "show", "affiche", "afficher", "search", "recherche", "rechercher", "client",
        "clients", "the", "for", "about", "pour", "sur", "avec", "and", "et", "ou",
        "open", "list", "liste", "today", "aujourd", "hui", "this", "week", "semaine",
        "globex", "employee", "assistant", "help", "moi", "me", "please", "svp",
    }
)


def _detect_ai_intent(message: str) -> str:
    m = message.lower()
    if llm_service.extract_tracking_number(message):
        return "tracking"
    if any(w in m for w in ("exception", "retard", "delay", "delayed", "livraison")):
        return "tracking"
    if any(w in m for w in ("notification", "notif", "non lu", "unread")):
        return "notifications"
    if any(w in m for w in ("admin", "escalad", "message admin", "contacter admin", "draft")):
        return "admin"
    if any(w in m for w in ("document", "pod", "export", "rapport", "archive")):
        return "document"
    if any(w in m for w in ("ticket", "support", "unresolved", "résolu", "pending", "escalated")):
        return "ticket"
    if any(w in m for w in ("client", "trouve", "find", "cherch", "customer", "utilisateur")):
        return "client"
    if any(w in m for w in ("résumé", "summary", "summarize", "résumer")):
        return "summary"
    return "general"


def _client_search_terms(message: str) -> list[str]:
    cleaned = _HTML_TAG_RE.sub("", message.lower())
    cleaned = re.sub(r"[^\w\s@.-]", " ", cleaned)
    return [w for w in cleaned.split() if len(w) > 2 and w not in _AI_STOP_WORDS]


def _resolve_clients(db: Session, message: str, limit: int = 5) -> list[EmployeeAiClientResult]:
    terms = _client_search_terms(message)
    stmt = select(User).where(User.role == UserRole.client.value)
    if terms:
        for term in terms[:4]:
            like = f"%{term}%"
            stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    else:
        like = f"%{message.strip().lower()[:40]}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    rows = list(db.scalars(stmt.order_by(User.created_at.desc()).limit(limit)).all())
    results: list[EmployeeAiClientResult] = []
    for c in rows:
        open_tk = int(
            db.scalar(
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.user_id == c.id, SupportTicket.status.in_(("open", "pending", "escalated")))
            )
            or 0
        )
        total_tr = int(
            db.scalar(select(func.count()).select_from(TrackingRequest).where(TrackingRequest.user_id == c.id)) or 0
        )
        total_doc = int(
            db.scalar(select(func.count()).select_from(ReportRun).where(ReportRun.generated_by_user_id == c.id)) or 0
        )
        results.append(
            EmployeeAiClientResult(
                id=c.id,
                full_name=c.full_name,
                email=c.email,
                company=_company_label(c),
                open_tickets=open_tk,
                total_trackings=total_tr,
                total_documents=total_doc,
            )
        )
    return results


def _resolve_tracking(db: Session, message: str) -> EmployeeAiTrackingResult | None:
    tn = llm_service.extract_tracking_number(message)
    status = ""
    location = ""
    eta = ""
    events: list[EmployeeAiTrackingEvent] = []
    client_name = ""
    is_exception = False

    if tn:
        row = db.scalar(
            select(TrackingRequest).where(func.lower(TrackingRequest.tracking_number) == tn.lower()).limit(1)
        )
        if row:
            u = db.get(User, row.user_id)
            client_name = u.full_name if u else ""
            status = row.status or ""
            location = row.current_location or ""
            eta = row.estimated_delivery or ""
            is_exception = _is_tracking_exception(row.status)
        try:
            data = fedex_service.get_shipment(tn)
            status = str(data.get("status") or status)
            location = str(data.get("current_location") or location)
            eta = str(data.get("estimated_delivery") or eta)
            is_exception = is_exception or _is_tracking_exception(status)
            for ev in (data.get("events") or [])[:6]:
                events.append(
                    EmployeeAiTrackingEvent(
                        label=str(ev.get("description") or ev.get("status") or "Event"),
                        at=str(ev.get("timestamp") or ev.get("date") or ""),
                    )
                )
        except Exception:
            pass
        if not events and row:
            events = [EmployeeAiTrackingEvent(label=status or "Recorded", at=str(row.created_at))]
        return EmployeeAiTrackingResult(
            tracking_number=tn,
            status=status or "Unknown",
            current_location=location or "—",
            estimated_delivery=eta or "—",
            is_exception=is_exception,
            client_name=client_name,
            events=events,
        )

    if any(w in message.lower() for w in ("exception", "retard", "delay")):
        row = db.scalar(
            select(TrackingRequest)
            .where(
                or_(
                    func.lower(TrackingRequest.status).like("%exception%"),
                    func.lower(TrackingRequest.status).like("%delay%"),
                    func.lower(TrackingRequest.status).like("%retard%"),
                )
            )
            .order_by(TrackingRequest.created_at.desc())
            .limit(1)
        )
        if row:
            u = db.get(User, row.user_id)
            return EmployeeAiTrackingResult(
                tracking_number=row.tracking_number,
                status=row.status or "Exception",
                current_location=row.current_location or "—",
                estimated_delivery=row.estimated_delivery or "—",
                is_exception=True,
                client_name=u.full_name if u else "",
                events=[EmployeeAiTrackingEvent(label=row.status or "Exception", at=str(row.created_at))],
            )
    return None


def _resolve_tickets(db: Session, message: str, limit: int = 6) -> list[EmployeeAiTicketResult]:
    m = message.lower()
    stmt = select(SupportTicket).options(joinedload(SupportTicket.user)).order_by(SupportTicket.created_at.desc())
    if any(w in m for w in ("unresolved", "open", "pending", "non résolu", "ouvert")):
        stmt = stmt.where(SupportTicket.status.in_(("open", "pending", "escalated")))
    elif "resolved" in m or "résolu" in m:
        stmt = stmt.where(SupportTicket.status == "resolved")
    elif "closed" in m or "fermé" in m:
        stmt = stmt.where(SupportTicket.status == "closed")
    terms = _client_search_terms(message)
    rows = list(db.scalars(stmt.limit(limit)).all())
    if terms and not rows:
        like = f"%{terms[0]}%"
        rows = list(
            db.scalars(
                select(SupportTicket)
                .options(joinedload(SupportTicket.user))
                .where(or_(func.lower(SupportTicket.subject).like(like), func.lower(SupportTicket.message).like(like)))
                .order_by(SupportTicket.created_at.desc())
                .limit(limit)
            ).all()
        )
    return [
        EmployeeAiTicketResult(
            id=t.id,
            ticket_number=t.ticket_number or generate_ticket_number(t.id),
            subject=t.subject,
            priority=t.priority or "medium",
            status=t.status,
            client_name=t.user.full_name if t.user else "—",
        )
        for t in rows
    ]


def _resolve_documents(db: Session, message: str, limit: int = 6) -> list[EmployeeAiDocumentResult]:
    items: list[EmployeeAiDocumentResult] = []
    terms = _client_search_terms(message)
    report_stmt = select(ReportRun).order_by(ReportRun.created_at.desc()).limit(limit)
    if terms:
        report_stmt = report_stmt.where(func.lower(ReportRun.name).like(f"%{terms[0]}%"))
    for r in db.scalars(report_stmt).all():
        uid = r.generated_by_user_id or 0
        u = db.get(User, uid) if uid else None
        items.append(
            EmployeeAiDocumentResult(
                id=f"report-{r.id}",
                title=r.name,
                doc_type="report" if r.format == "pdf" else "export",
                created_at=r.created_at,
                client_name=u.full_name if u else "—",
            )
        )
    tr_stmt = select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(limit)
    if terms:
        tr_stmt = tr_stmt.where(func.lower(TrackingRequest.tracking_number).like(f"%{terms[0]}%"))
    for t in db.scalars(tr_stmt).all():
        u = db.get(User, t.user_id)
        items.append(
            EmployeeAiDocumentResult(
                id=f"tracking-{t.id}",
                title=f"POD / {t.tracking_number}",
                doc_type="proof" if (t.status or "").lower() in ("delivered", "livré") else "tracking",
                created_at=t.created_at,
                client_name=u.full_name if u else "—",
                tracking_number=t.tracking_number,
            )
        )
    return items[:limit]


def _build_ai_actions(intent: str, clients, tracking, tickets, documents) -> list[EmployeeAiAction]:
    actions: list[EmployeeAiAction] = []
    if intent == "client" and clients:
        c = clients[0]
        actions.extend(
            [
                EmployeeAiAction(label="Open Client", route=f"/employee/client/{c.id}", kind="open_client"),
                EmployeeAiAction(label="Open Tracking", route="/employee/tracking", kind="open_tracking"),
                EmployeeAiAction(label="Open Documents", route="/employee/clients", kind="open_documents"),
            ]
        )
    if intent == "tracking" and tracking:
        actions.extend(
            [
                EmployeeAiAction(
                    label="View Tracking",
                    route=f"/employee/tracking/{tracking.tracking_number}",
                    kind="open_tracking",
                ),
                EmployeeAiAction(label="All Operations", route="/employee/tracking", kind="open_tracking"),
            ]
        )
    if intent == "ticket" and tickets:
        t = tickets[0]
        actions.extend(
            [
                EmployeeAiAction(label="Open Ticket", route=f"/employee/support/{t.id}", kind="open_ticket"),
                EmployeeAiAction(label="Reply", route=f"/employee/support/{t.id}", kind="reply_ticket"),
                EmployeeAiAction(label="Escalate", route=f"/employee/support/{t.id}", kind="escalate"),
            ]
        )
    if intent == "document" and documents:
        actions.append(EmployeeAiAction(label="Documents Center", route="/employee/clients", kind="open_documents"))
    if intent == "admin":
        actions.extend(
            [
                EmployeeAiAction(label="Chat with Admin", route="/employee/admin-chat", kind="admin_chat"),
                EmployeeAiAction(label="Support Tickets", route="/employee/support", kind="open_ticket"),
            ]
        )
    if intent == "notifications":
        actions.append(EmployeeAiAction(label="Notifications", route="/employee/notifications", kind="notifications"))
    return actions


def _compose_ai_reply(
    intent: str,
    message: str,
    clients: list[EmployeeAiClientResult],
    tracking: EmployeeAiTrackingResult | None,
    tickets: list[EmployeeAiTicketResult],
    documents: list[EmployeeAiDocumentResult],
    admin_draft: str | None,
    llm_reply: str,
) -> str:
    parts: list[str] = []
    if intent == "client" and clients:
        parts.append(f"**{len(clients)} client(s) found** for your query.")
        for c in clients[:3]:
            parts.append(f"- **{c.full_name}** ({c.email}) — {c.open_tickets} open ticket(s), {c.total_trackings} shipment(s)")
    elif intent == "tracking" and tracking:
        badge = "**Exception**" if tracking.is_exception else "In transit"
        parts.append(f"**Tracking {tracking.tracking_number}** · {badge}")
        parts.append(f"- **Status:** {tracking.status}")
        parts.append(f"- **Location:** {tracking.current_location}")
        parts.append(f"- **ETA:** {tracking.estimated_delivery}")
        if tracking.client_name:
            parts.append(f"- **Client:** {tracking.client_name}")
    elif intent == "ticket" and tickets:
        parts.append(f"**{len(tickets)} ticket(s)** matching your request:")
        for t in tickets[:4]:
            parts.append(f"- `{t.ticket_number}` **{t.subject}** · {t.priority} · {t.status}")
    elif intent == "document" and documents:
        parts.append(f"**{len(documents)} document(s)** found:")
        for d in documents[:4]:
            parts.append(f"- **{d.title}** ({d.doc_type}) — {d.client_name}")
    elif intent == "admin" and admin_draft:
        parts.append("**Draft message for admin:**")
        parts.append(f"> {admin_draft}")
    elif intent == "notifications":
        parts.append("Check the **Notifications** panel for unread items and recent alerts.")
    if llm_reply and intent == "general":
        parts.append(llm_reply)
    elif llm_reply and not parts:
        parts.append(llm_reply)
    elif llm_reply and intent != "general":
        parts.append("")
        parts.append(llm_reply)
    return "\n".join(parts) if parts else llm_reply or "I could not find operational data for this request."


def _build_chat_context_panel(db: Session, employee: User) -> EmployeeChatContextPanel:
    client_rows = list(
        db.scalars(
            select(User).where(User.role == UserRole.client.value).order_by(User.created_at.desc()).limit(5)
        ).all()
    )
    recent_clients = []
    for c in client_rows:
        last_tr = db.scalar(
            select(TrackingRequest).where(TrackingRequest.user_id == c.id).order_by(TrackingRequest.created_at.desc()).limit(1)
        )
        open_tk = int(
            db.scalar(
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.user_id == c.id, SupportTicket.status.in_(("open", "pending", "escalated")))
            )
            or 0
        )
        activity = f"{last_tr.tracking_number} · {last_tr.status}" if last_tr else "No activity"
        recent_clients.append(
            EmployeeDashboardClientWidget(
                id=c.id,
                full_name=c.full_name,
                company=_company_label(c),
                email=c.email,
                last_activity=activity,
                avatar_initials=_initials(c.full_name),
                open_tickets=open_tk,
            )
        )

    ticket_rows = list(
        db.scalars(
            select(SupportTicket)
            .options(joinedload(SupportTicket.user))
            .order_by(SupportTicket.created_at.desc())
            .limit(5)
        ).all()
    )
    recent_tickets = [
        EmployeeDashboardTicketWidget(
            id=t.id,
            ticket_number=t.ticket_number or generate_ticket_number(t.id),
            subject=t.subject,
            priority=t.priority or "medium",
            status=t.status,
            client_name=t.user.full_name if t.user else "—",
            created_at=t.created_at,
        )
        for t in ticket_rows
    ]

    all_tr = list(db.scalars(select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(80)).all())
    tr_users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({t.user_id for t in all_tr}))).all()}
    tracking_exceptions = [
        EmployeeDashboardTrackingEvent(
            tracking_number=t.tracking_number,
            status=t.status or "—",
            client_name=tr_users[t.user_id].full_name if t.user_id in tr_users else "—",
            created_at=t.created_at,
            is_exception=True,
        )
        for t in all_tr
        if _is_tracking_exception(t.status)
    ][:5]

    unread_notification_count = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == employee.id, ClientNotification.is_read.is_(False))
        )
        or 0
    )
    notif_rows = list(
        db.scalars(
            select(ClientNotification)
            .where(ClientNotification.user_id == employee.id)
            .order_by(ClientNotification.created_at.desc())
            .limit(5)
        ).all()
    )
    unread_notifications = []
    for n in notif_rows:
        payload = employee_notification_to_dict(n)
        payload["message"] = payload["message"][:120]
        unread_notifications.append(EmployeeNotificationRead.model_validate(payload))

    admin_rows = list(
        db.scalars(
            select(EmployeeAdminMessage)
            .where(EmployeeAdminMessage.employee_id == employee.id)
            .order_by(EmployeeAdminMessage.created_at.desc())
            .limit(5)
        ).all()
    )
    unread_admin_count = sum(1 for m in admin_rows if m.sender_role == "admin" and not m.is_read)
    admin_messages = [_admin_msg_read(m, db) for m in reversed(admin_rows[-5:])]

    return EmployeeChatContextPanel(
        recent_clients=recent_clients,
        recent_tickets=recent_tickets,
        tracking_exceptions=tracking_exceptions,
        unread_notifications=unread_notifications,
        admin_messages=admin_messages,
        unread_admin_count=unread_admin_count,
        unread_notification_count=unread_notification_count,
    )


def _build_employee_context(db: Session, message: str) -> str:
    parts: list[str] = []
    clients = _resolve_clients(db, message, limit=3)
    if clients:
        parts.append("Clients: " + ", ".join(f"{c.full_name} ({c.email})" for c in clients))
    tn = llm_service.extract_tracking_number(message)
    if tn:
        parts.append(f"Tracking: {tn}")
    open_tickets = _resolve_tickets(db, message, limit=5)
    if open_tickets:
        parts.append("Tickets: " + "; ".join(f"{t.ticket_number} {t.subject}" for t in open_tickets))
    return "\n".join(parts)


@router.get("/chat/context", response_model=EmployeeChatContextPanel)
def employee_chat_context(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeChatContextPanel:
    return _build_chat_context_panel(db, employee)


@router.post("/chat/ai", response_model=EmployeeAiResponse)
def employee_ai_chat(
    payload: EmployeeAiRequest,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAiResponse:
    intent = _detect_ai_intent(payload.message)
    clients: list[EmployeeAiClientResult] = []
    tracking: EmployeeAiTrackingResult | None = None
    tickets: list[EmployeeAiTicketResult] = []
    documents: list[EmployeeAiDocumentResult] = []
    admin_draft: str | None = None

    if intent in ("client", "summary", "general"):
        clients = _resolve_clients(db, payload.message)
        if clients and intent == "general":
            intent = "client"
    if intent == "tracking":
        tracking = _resolve_tracking(db, payload.message)
    if intent in ("ticket", "summary", "admin"):
        tickets = _resolve_tickets(db, payload.message)
    if intent == "document":
        documents = _resolve_documents(db, payload.message)
    if intent == "admin":
        preview = payload.message[:200]
        admin_draft = (
            f"Hello Admin,\n\nI need assistance regarding: {preview}\n\n"
            f"Could you please review and advise on the next steps?\n\nBest regards,\n{employee.full_name}"
        )

    context = _build_employee_context(db, payload.message)
    system_extra = (
        "Tu es Globex Employee AI Assistant, copilote opérationnel pour les employés Globex FedEx. "
        "Réponds de façon professionnelle, concise, en markdown léger si utile.\n"
    )
    if context:
        system_extra += f"\nContexte:\n{context}\n"

    llm_reply = ""
    try:
        result = llm_service.generate_response(
            payload.message,
            response_preferences=employee.response_preferences or system_extra,
            preferred_name=employee.full_name,
            ui_language=employee.preferred_language,
        )
        llm_reply = result.reply
    except Exception:
        llm_reply = ""

    reply = _compose_ai_reply(intent, payload.message, clients, tracking, tickets, documents, admin_draft, llm_reply)
    actions = _build_ai_actions(intent, clients, tracking, tickets, documents)

    return EmployeeAiResponse(
        reply=reply,
        intent=intent,
        context_used=bool(context or clients or tracking or tickets or documents),
        clients=clients,
        tracking=tracking,
        tickets=tickets,
        documents=documents,
        admin_draft=admin_draft,
        actions=actions,
    )


# ── Globex AI Agent ────────────────────────────────────────────────────────────


def _detect_ai_agent_intent(message: str) -> str:
    m = message.lower()
    if any(w in m for w in ("créer ticket", "create ticket", "nouveau ticket", "new ticket")):
        return "create_ticket"
    if any(w in m for w in ("support summary", "create summary", "résumé support")):
        return "create_summary"
    if any(w in m for w in ("draft response", "generate reply", "brouillon réponse", "répondre au client")):
        return "draft_response"
    if any(w in m for w in ("résumé", "summary", "summarize")) and llm_service.extract_tracking_number(message):
        return "summarize_shipment"
    if any(w in m for w in ("résumé", "summary", "summarize", "summarize client")) and any(
        w in m for w in ("client", "compte", "account", "profil")
    ):
        return "summarize_client"
    if llm_service.extract_tracking_number(message):
        if any(w in m for w in ("résumé", "summary", "summarize", "statut")):
            return "summarize_shipment"
        return "search_tracking"
    if any(w in m for w in ("exception", "retard", "delay", "delayed")) and any(w in m for w in ("today", "aujourd", "hui")):
        return "delivery_exceptions"
    if any(w in m for w in ("exception", "retard", "delay", "delayed", "delivery exception")):
        return "delivery_exceptions"
    if any(w in m for w in ("draft", "message admin", "contacter admin", "contact admin", "draft admin")):
        return "draft_admin_message"
    if any(w in m for w in ("admin", "escalad")) and "client" not in m:
        return "draft_admin_message"
    if any(w in m for w in ("pending document", "documents en attente")):
        return "pending_documents"
    if any(w in m for w in ("document", "pod", "export", "rapport")):
        return "pending_documents"
    if any(w in m for w in ("unresolved", "open ticket", "tickets ouverts", "open tickets")):
        return "list_open_tickets"
    if any(w in m for w in ("ticket", "support")):
        return "list_open_tickets"
    if any(w in m for w in ("client", "trouve", "find", "cherch", "customer")):
        return "search_client"
    if any(w in m for w in ("tracking", "colis", "shipment", "suivi")):
        return "search_tracking"
    return "general_question"


def _map_agent_to_legacy_intent(agent_intent: str) -> str:
    mapping = {
        "search_client": "client",
        "summarize_client": "summary",
        "search_tracking": "tracking",
        "summarize_shipment": "tracking",
        "delivery_exceptions": "tracking",
        "list_open_tickets": "ticket",
        "pending_documents": "document",
        "draft_admin_message": "admin",
        "draft_response": "general",
        "create_summary": "ticket",
        "create_ticket": "ticket",
        "general_question": "general",
    }
    return mapping.get(agent_intent, "general")


def _agent_tracking_from_row(db: Session, row: TrackingRequest) -> EmployeeAiTrackingResult:
    u = db.get(User, row.user_id)
    return EmployeeAiTrackingResult(
        tracking_number=row.tracking_number,
        status=row.status or "Unknown",
        current_location=row.current_location or "—",
        estimated_delivery=row.estimated_delivery or "—",
        is_exception=_is_tracking_exception(row.status),
        client_name=u.full_name if u else "",
        events=[EmployeeAiTrackingEvent(label=row.status or "Update", at=str(row.created_at))],
    )


def _resolve_agent_exceptions(db: Session, limit: int = 6) -> list[EmployeeAiTrackingResult]:
    rows = list(
        db.scalars(
            select(TrackingRequest)
            .where(
                or_(
                    func.lower(TrackingRequest.status).like("%exception%"),
                    func.lower(TrackingRequest.status).like("%delay%"),
                    func.lower(TrackingRequest.status).like("%retard%"),
                )
            )
            .order_by(TrackingRequest.created_at.desc())
            .limit(limit)
        ).all()
    )
    return [_agent_tracking_from_row(db, row) for row in rows]


def _build_ai_agent_cards(
    intent: str,
    clients: list[EmployeeAiClientResult],
    tracking: EmployeeAiTrackingResult | None,
    tickets: list[EmployeeAiTicketResult],
    documents: list[EmployeeAiDocumentResult],
    admin_draft: str | None,
    extra_shipments: list[EmployeeAiTrackingResult] | None = None,
) -> list[EmployeeAiAgentCard]:
    cards: list[EmployeeAiAgentCard] = []
    for c in clients[:5]:
        cards.append(
            EmployeeAiAgentCard(
                type="client",
                title=c.full_name,
                subtitle=c.email,
                meta={
                    "shipments": c.total_trackings,
                    "tickets": c.open_tickets,
                    "documents": c.total_documents,
                    "company": c.company,
                },
                actions=[
                    EmployeeAiAgentCardAction(label="Open profile", route=f"/employee/client/{c.id}"),
                    EmployeeAiAgentCardAction(label="View shipments", route=f"/employee/client/{c.id}?tab=shipments"),
                    EmployeeAiAgentCardAction(label="Open tickets", route=f"/employee/client/{c.id}?tab=tickets"),
                ],
            )
        )
    shipments: list[EmployeeAiTrackingResult] = []
    if tracking:
        shipments.append(tracking)
    for extra in extra_shipments or []:
        if extra.tracking_number not in {s.tracking_number for s in shipments}:
            shipments.append(extra)
    for tr in shipments[:8]:
        cards.append(
            EmployeeAiAgentCard(
                type="shipment",
                title=tr.tracking_number,
                subtitle=tr.status,
                meta={
                    "location": tr.current_location,
                    "eta": tr.estimated_delivery,
                    "client": tr.client_name,
                    "is_exception": tr.is_exception,
                    "events": [e.model_dump() for e in tr.events[:4]],
                },
                actions=[
                    EmployeeAiAgentCardAction(label="Open shipment", route=f"/employee/tracking/{tr.tracking_number}"),
                    EmployeeAiAgentCardAction(label="Track live", route=f"/employee/tracking/{tr.tracking_number}"),
                    EmployeeAiAgentCardAction(label="Export", route="/employee/documents"),
                ],
            )
        )
    for t in tickets[:6]:
        cards.append(
            EmployeeAiAgentCard(
                type="ticket",
                title=t.subject,
                subtitle=f"{t.ticket_number} · {t.client_name}",
                meta={"priority": t.priority, "status": t.status},
                actions=[
                    EmployeeAiAgentCardAction(label="Open ticket", route=f"/employee/support/{t.id}"),
                    EmployeeAiAgentCardAction(label="Reply", route=f"/employee/support/{t.id}"),
                    EmployeeAiAgentCardAction(label="Resolve", route=f"/employee/support/{t.id}"),
                ],
            )
        )
    for d in documents[:6]:
        route = "/employee/documents"
        cards.append(
            EmployeeAiAgentCard(
                type="document",
                title=d.title,
                subtitle=f"{d.doc_type} · {d.client_name}",
                meta={"doc_type": d.doc_type, "created_at": d.created_at.isoformat()},
                actions=[
                    EmployeeAiAgentCardAction(label="Preview", route=route),
                    EmployeeAiAgentCardAction(label="Download", route=route),
                ],
            )
        )
    if admin_draft:
        cards.append(
            EmployeeAiAgentCard(
                type="admin_draft",
                title="Admin message draft",
                subtitle="Ready to review and send",
                meta={"draft": admin_draft},
                actions=[
                    EmployeeAiAgentCardAction(
                        label="Send to admin",
                        route=f"/employee/admin-chat?draft={admin_draft[:120]}",
                    ),
                ],
            )
        )
    return cards


def _agent_message_to_read(msg: AiAgentMessage) -> EmployeeAiAgentMessageRead:
    cards_raw = ai_agent_service.parse_cards(msg.cards_json)
    cards = [EmployeeAiAgentCard(**item) for item in cards_raw]
    return EmployeeAiAgentMessageRead(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        intent=msg.intent or "",
        cards=cards,
        created_at=msg.created_at,
    )


def _build_ai_agent_live_context(db: Session, employee: User) -> EmployeeAiAgentLiveContext:
    panel = _build_chat_context_panel(db, employee)
    all_tr = list(db.scalars(select(TrackingRequest).order_by(TrackingRequest.created_at.desc()).limit(8)).all())
    tr_users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({t.user_id for t in all_tr}))).all()}
    recent_shipments = [
        EmployeeDashboardTrackingEvent(
            tracking_number=t.tracking_number,
            status=t.status or "—",
            client_name=tr_users[t.user_id].full_name if t.user_id in tr_users else "—",
            created_at=t.created_at,
            is_exception=_is_tracking_exception(t.status),
        )
        for t in all_tr
    ]
    pending_documents = _resolve_documents(db, "pending", limit=6)
    return EmployeeAiAgentLiveContext(
        recent_clients=panel.recent_clients,
        recent_shipments=recent_shipments,
        recent_tickets=panel.recent_tickets,
        pending_documents=pending_documents,
        tracking_exceptions=panel.tracking_exceptions,
        unread_notification_count=panel.unread_notification_count,
        unread_admin_count=panel.unread_admin_count,
    )


@router.get("/ai-agent/live-context", response_model=EmployeeAiAgentLiveContext)
def employee_ai_agent_live_context(
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAiAgentLiveContext:
    return _build_ai_agent_live_context(db, employee)


@router.get("/ai-agent/conversations", response_model=list[EmployeeAiAgentConversationSummary])
def list_ai_agent_conversations(
    search: str | None = Query(None, max_length=120),
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> list[EmployeeAiAgentConversationSummary]:
    rows = ai_agent_service.list_conversations(db, employee_id=employee.id, search=search)
    return [
        EmployeeAiAgentConversationSummary(
            id=row.id,
            title=row.title,
            preview=ai_agent_service.conversation_preview(row),
            group=ai_agent_service.conversation_group(row.updated_at),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/ai-agent/conversations", response_model=EmployeeAiAgentConversationDetail)
def create_ai_agent_conversation(
    payload: EmployeeAiAgentConversationCreate,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAiAgentConversationDetail:
    conv = ai_agent_service.create_conversation(db, employee_id=employee.id, title=payload.title)
    db.commit()
    db.refresh(conv)
    return EmployeeAiAgentConversationDetail(
        id=conv.id,
        title=conv.title,
        messages=[],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/ai-agent/conversations/{conversation_id}", response_model=EmployeeAiAgentConversationDetail)
def get_ai_agent_conversation(
    conversation_id: str,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAiAgentConversationDetail:
    conv = ai_agent_service.get_conversation(db, employee_id=employee.id, conversation_id=conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable.")
    return EmployeeAiAgentConversationDetail(
        id=conv.id,
        title=conv.title,
        messages=[_agent_message_to_read(m) for m in conv.messages],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.patch("/ai-agent/conversations/{conversation_id}", response_model=EmployeeAiAgentConversationSummary)
def update_ai_agent_conversation(
    conversation_id: str,
    payload: EmployeeAiAgentConversationUpdate,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAiAgentConversationSummary:
    conv = ai_agent_service.get_conversation(db, employee_id=employee.id, conversation_id=conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable.")
    ai_agent_service.update_conversation_title(db, conv=conv, title=payload.title)
    ai_agent_service.log_action(
        db, employee_id=employee.id, action_type="conversation_rename", target_type="conversation", target_id=conv.id
    )
    db.commit()
    db.refresh(conv)
    return EmployeeAiAgentConversationSummary(
        id=conv.id,
        title=conv.title,
        preview=ai_agent_service.conversation_preview(conv),
        group=ai_agent_service.conversation_group(conv.updated_at),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/ai-agent/conversations/{conversation_id}")
def delete_ai_agent_conversation(
    conversation_id: str,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    conv = ai_agent_service.get_conversation(db, employee_id=employee.id, conversation_id=conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable.")
    ai_agent_service.log_action(
        db, employee_id=employee.id, action_type="conversation_delete", target_type="conversation", target_id=conv.id
    )
    ai_agent_service.delete_conversation(db, conv=conv)
    db.commit()
    return {"deleted": True}


@router.post("/ai-agent/message", response_model=EmployeeAiAgentMessageResponse)
def employee_ai_agent_message(
    payload: EmployeeAiAgentMessageRequest,
    request: Request,
    employee: User = Depends(require_role(UserRole.employe.value)),
    db: Session = Depends(get_db),
) -> EmployeeAiAgentMessageResponse:
    message = _sanitize_text(payload.message.strip())
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message requis.")

    conv = None
    if payload.conversationId:
        conv = ai_agent_service.get_conversation(db, employee_id=employee.id, conversation_id=payload.conversationId)
    if not conv:
        conv = ai_agent_service.create_conversation(db, employee_id=employee.id)
    ai_agent_service.add_message(db, conversation=conv, role="user", content=message)

    agent_intent = _detect_ai_agent_intent(message)
    legacy_intent = _map_agent_to_legacy_intent(agent_intent)
    clients: list[EmployeeAiClientResult] = []
    tracking: EmployeeAiTrackingResult | None = None
    extra_shipments: list[EmployeeAiTrackingResult] = []
    tickets: list[EmployeeAiTicketResult] = []
    documents: list[EmployeeAiDocumentResult] = []
    admin_draft: str | None = None

    if agent_intent in ("search_client", "summarize_client"):
        clients = _resolve_clients(db, message)
    elif agent_intent in ("search_tracking", "summarize_shipment", "create_ticket"):
        tracking = _resolve_tracking(db, message)
    elif agent_intent == "delivery_exceptions":
        extra_shipments = _resolve_agent_exceptions(db, limit=6)
        tracking = _resolve_tracking(db, message) if llm_service.extract_tracking_number(message) else None
        if not tracking and extra_shipments:
            tracking = extra_shipments[0]
    elif agent_intent in ("list_open_tickets", "create_summary"):
        tickets = _resolve_tickets(db, message)
    elif agent_intent == "pending_documents":
        documents = _resolve_documents(db, message)
    elif agent_intent == "draft_admin_message":
        preview = message[:200]
        admin_draft = (
            f"Hello Admin,\n\nI need assistance regarding: {preview}\n\n"
            f"Could you please review and advise on the next steps?\n\nBest regards,\n{employee.full_name}"
        )
    elif agent_intent == "draft_response":
        clients = _resolve_clients(db, message)
        client_name = clients[0].full_name if clients else "the client"
        admin_draft = (
            f"Dear {client_name},\n\nThank you for contacting Globex FedEx. "
            f"Regarding your request: {message[:180]}\n\n"
            f"We are reviewing the details and will follow up shortly.\n\nBest regards,\n{employee.full_name}"
        )

    context = _build_employee_context(db, message)
    system_extra = (
        "Tu es Globex AI Agent, assistant opérationnel pour employés logistiques Globex FedEx. "
        "Réponds de façon professionnelle et concise.\n"
    )
    if context:
        system_extra += f"\nContexte:\n{context}\n"

    llm_reply = ""
    try:
        result = llm_service.generate_response(
            message,
            response_preferences=employee.response_preferences or system_extra,
            preferred_name=employee.full_name,
            ui_language=employee.preferred_language,
        )
        llm_reply = result.reply
    except Exception:
        llm_reply = ""

    reply = _compose_ai_reply(legacy_intent, message, clients, tracking, tickets, documents, admin_draft, llm_reply)
    cards = _build_ai_agent_cards(agent_intent, clients, tracking, tickets, documents, admin_draft, extra_shipments)
    actions = _build_ai_actions(legacy_intent, clients, tracking, tickets, documents)
    assistant_msg = ai_agent_service.add_message(
        db, conversation=conv, role="assistant", content=reply, intent=agent_intent, cards=cards
    )
    ai_agent_service.log_action(
        db, employee_id=employee.id, action_type="agent_message", target_type="conversation", target_id=conv.id
    )
    write_log(
        db,
        action="employee.ai_agent_message",
        message=f"AI Agent — {agent_intent}",
        category="system",
        level="INFO",
        actor_user_id=employee.id,
        ip_address=client_ip(request),
        metadata={"intent": agent_intent, "conversation_id": conv.id},
        commit=False,
    )
    db.commit()

    return EmployeeAiAgentMessageResponse(
        reply=reply,
        intent=agent_intent,
        conversationId=conv.id,
        cards=cards,
        actions=actions,
        createdAt=assistant_msg.created_at,
    )


admin_employee_chat_router = APIRouter(prefix="/api/admin/employee-chat", tags=["admin-employee-chat"])


@admin_employee_chat_router.get("", response_model=list[AdminEmployeeChatListItem])
def admin_list_employee_chats(
    q: str | None = Query(default=None),
    admin: User = Depends(require_role(UserRole.admin.value)),
    db: Session = Depends(get_db),
) -> list[AdminEmployeeChatListItem]:
    del admin
    stmt = select(User).where(User.role == UserRole.employe.value, User.status == UserStatus.active.value)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    employees = list(db.scalars(stmt.order_by(User.full_name.asc())).all())
    items: list[AdminEmployeeChatListItem] = []
    for emp in employees:
        rows = _admin_chat_rows(db, emp.id)
        unread = sum(1 for r in rows if r.sender_role == "employe" and not r.is_read)
        last = rows[-1] if rows else None
        items.append(
            AdminEmployeeChatListItem(
                id=emp.id,
                full_name=emp.full_name,
                email=emp.email,
                avatar_initial=_initials(emp.full_name or emp.email),
                unread_count=unread,
                last_message=(last.body[:120] if last else ""),
                last_message_at=last.created_at if last else None,
            )
        )
    items.sort(key=lambda x: (x.unread_count == 0, -(x.last_message_at.timestamp() if x.last_message_at else 0)))
    return items


@admin_employee_chat_router.get("/{employee_id}/messages", response_model=EmployeeAdminChatResponse)
def admin_get_employee_messages(
    employee_id: int,
    admin: User = Depends(require_role(UserRole.admin.value)),
    db: Session = Depends(get_db),
) -> EmployeeAdminChatResponse:
    del admin
    emp = db.get(User, employee_id)
    if emp is None or emp.role != UserRole.employe.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable.")
    rows = _admin_chat_rows(db, employee_id)
    for r in rows:
        if r.sender_role in ("employe", "employee") and not r.is_read:
            r.is_read = True
    db.commit()
    return EmployeeAdminChatResponse(
        items=[_admin_msg_read(r, db) for r in rows],
        unread_count=0,
    )


@admin_employee_chat_router.post("/{employee_id}/messages", response_model=EmployeeAdminMessageRead)
def admin_reply_employee(
    employee_id: int,
    payload: EmployeeAdminMessageCreate,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_role(UserRole.admin.value)),
    db: Session = Depends(get_db),
) -> EmployeeAdminMessageRead:
    emp = db.get(User, employee_id)
    if emp is None or emp.role != UserRole.employe.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable.")
    body = _HTML_TAG_RE.sub("", payload.body).strip()
    if not body and not payload.attachment_url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message requis.")
    row = EmployeeAdminMessage(
        employee_id=employee_id,
        sender_user_id=admin.id,
        sender_role="admin",
        body=body,
        attachment_url=payload.attachment_url,
        is_read=False,
    )
    db.add(row)
    notify_employee_admin_message(db, employee_id=employee_id, admin_id=admin.id, body=body)
    db.commit()
    db.refresh(row)
    read_row = _admin_msg_read(row, db)
    unread = _admin_chat_unread(_admin_chat_rows(db, employee_id))
    background_tasks.add_task(
        _broadcast_admin_chat_message,
        employee_id,
        read_row.model_dump(mode="json"),
        unread,
    )
    return read_row


@admin_employee_chat_router.post("/{employee_id}/typing")
async def admin_typing_employee(
    employee_id: int,
    payload: EmployeeAdminChatTyping,
    admin: User = Depends(require_role(UserRole.admin.value)),
) -> dict[str, bool]:
    await employee_admin_chat_hub.set_typing(
        employee_id,
        sender_role="admin",
        sender_name=admin.full_name or "Admin",
        active=payload.active,
    )
    return {"ok": True}


def _authenticate_ws_token(token: str, db: Session) -> User | None:
    payload = decode_access_token(token)
    if payload is None:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    token_id = payload.get("jti")
    user = db.get(User, user_id)
    if user is None or not token_id:
        return None
    row = db.query(UserSession).filter(UserSession.token_id == token_id, UserSession.is_active.is_(True)).one_or_none()
    if row is None or row.user_id != user.id:
        return None
    return user


@router.websocket("/admin-chat/ws")
async def admin_chat_websocket(websocket: WebSocket, token: str = Query(default="")) -> None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    user: User | None = None
    try:
        user = _authenticate_ws_token(token, db)
        if user is None or user.role != UserRole.employe.value:
            await websocket.close(code=4401)
            return
        await employee_admin_chat_hub.connect(user.id, websocket)
        typing = employee_admin_chat_hub.get_typing(user.id)
        if typing:
            await websocket.send_json(
                {
                    "type": "typing",
                    "payload": {
                        "sender_role": typing.sender_role,
                        "sender_name": typing.sender_name,
                        "active": True,
                    },
                }
            )
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "typing":
                payload = data.get("payload") or {}
                await employee_admin_chat_hub.set_typing(
                    user.id,
                    sender_role="employe",
                    sender_name=user.full_name or "Employee",
                    active=bool(payload.get("active", True)),
                )
    except WebSocketDisconnect:
        pass
    finally:
        if user is not None:
            await employee_admin_chat_hub.disconnect(user.id, websocket)
        db.close()
