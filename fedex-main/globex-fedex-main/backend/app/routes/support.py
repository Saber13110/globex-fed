from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.client_notification import ClientNotification
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.support_ticket_message import SupportTicketMessage
from app.models.user import User
from app.routes.deps import get_current_user, require_role
from app.schemas.support import (
    ClientNotificationListResponse,
    ClientNotificationRead,
    FaqListResponse,
    SupportMessageCreate,
    SupportTicketCreate,
    SupportTicketAdminDetailRead,
    SupportTicketCreatedResponse,
    SupportTicketDetailRead,
    SupportTicketListResponse,
    SupportTicketMessageRead,
    SupportTicketRead,
    SupportTicketStatusUpdate,
)
from app.services.activity_log_service import client_ip, write_log
from app.services.faq_service import load_faq
from app.services.help_center_service import generate_ticket_number
from app.services.support_ticket_service import create_client_support_ticket, sanitize_support_text
from app.services.support_attachment_service import (
    attachment_file_path,
    display_filename,
    save_support_attachment,
    validate_stored_name,
)
from app.services.employee_notification_service import (
    notify_employee_ticket_admin_reply,
    notify_employees_ticket_user_reply,
)
from app.services.user_notification_service import (
    create_user_notification,
    notify_admins_support_user_reply,
)

router = APIRouter(prefix="/support", tags=["support"])

def _sanitize_text(value: str) -> str:
    return sanitize_support_text(value)


def _ticket_to_read(ticket: SupportTicket) -> SupportTicketRead:
    return SupportTicketRead(
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
    )


def _message_to_read(row: SupportTicketMessage) -> SupportTicketMessageRead:
    author_name = None
    if row.author and row.author_role == "admin":
        author_name = row.author.full_name or "Admin"
    elif row.author and row.author_role == "user":
        author_name = row.author.full_name
    return SupportTicketMessageRead(
        id=row.id,
        author_role=row.author_role,
        body=row.body,
        attachment_url=row.attachment_url,
        created_at=row.created_at,
        author_name=author_name,
    )


def _client_notif_to_read(row: ClientNotification) -> ClientNotificationRead:
    return ClientNotificationRead(
        id=row.id,
        kind=row.kind,
        type=row.kind,
        title=row.title,
        message=row.message,
        link=row.link,
        reference_id=row.reference_id,
        related_ticket_id=row.reference_id,
        related_tracking_number=row.related_tracking_number or "",
        priority=row.priority or "medium",
        sender_id=row.sender_id,
        sender_role=row.sender_role,
        status="read" if row.is_read else "unread",
        is_read=row.is_read,
        created_at=row.created_at,
        read_at=row.read_at,
    )


def _ensure_ticket_owner(ticket: SupportTicket | None, user: User) -> SupportTicket:
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    if ticket.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    return ticket


def _attachment_public_url(request: Request, stored_name: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/support/attachments/{stored_name}"


def _message_allowed(body: str, attachment_url: str | None) -> bool:
    return bool(body.strip() or (attachment_url and attachment_url.strip()))


@router.post("/attachments")
async def upload_support_attachment(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    del current_user
    try:
        stored = await save_support_attachment(file)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "url": _attachment_public_url(request, stored),
        "filename": file.filename or display_filename(stored),
    }


@router.get("/attachments/{stored_name}")
def get_support_attachment(
    stored_name: str,
    _: User = Depends(get_current_user),
) -> FileResponse:
    try:
        safe_name = validate_stored_name(stored_name)
        path = attachment_file_path(safe_name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fichier introuvable.") from exc
    return FileResponse(path, filename=display_filename(safe_name))


@router.get("/faq", response_model=FaqListResponse)
def get_faq(
    lang: str | None = Query(default=None, max_length=8),
) -> FaqListResponse:
    items, language = load_faq(lang)
    return FaqListResponse(items=items, language=language)


def _list_user_tickets(current_user: User, db: Session) -> SupportTicketListResponse:
    rows = list(
        db.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == current_user.id)
            .order_by(SupportTicket.updated_at.desc(), SupportTicket.created_at.desc())
        ).all()
    )
    return SupportTicketListResponse(items=[_ticket_to_read(t) for t in rows])


@router.get("/tickets", response_model=SupportTicketListResponse)
def list_support_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupportTicketListResponse:
    return _list_user_tickets(current_user, db)


@router.get("/tickets/me", response_model=SupportTicketListResponse)
def list_my_support_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupportTicketListResponse:
    return _list_user_tickets(current_user, db)


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetailRead)
def get_support_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupportTicketDetailRead:
    ticket = db.scalar(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages).joinedload(SupportTicketMessage.author))
        .where(SupportTicket.id == ticket_id)
    )
    ticket = _ensure_ticket_owner(ticket, current_user)
    base = _ticket_to_read(ticket)
    return SupportTicketDetailRead(
        **base.model_dump(),
        messages=[_message_to_read(m) for m in ticket.messages],
    )


@router.post("/tickets", response_model=SupportTicketCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_support_ticket(
    payload: SupportTicketCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupportTicketCreatedResponse:
    try:
        created = create_client_support_ticket(
            db,
            user=current_user,
            subject=payload.subject,
            message=payload.message,
            category=payload.category,
            priority=payload.priority,
            attachment_url=payload.attachmentUrl,
            ip_address=client_ip(request),
            commit=True,
        )
    except ValueError as exc:
        detail = "Subject required." if "Subject" in str(exc) else "Message required."
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from exc
    return SupportTicketCreatedResponse(
        success=True,
        ticketId=created["ticket_number"],
        id=created["ticket_id"],
        status=created["status"],
        createdAt=created["created_at"],
    )


@router.post("/tickets/{ticket_id}/messages", response_model=SupportTicketMessageRead)
def add_support_message(
    ticket_id: int,
    payload: SupportMessageCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupportTicketMessageRead:
    ticket = _ensure_ticket_owner(db.get(SupportTicket, ticket_id), current_user)
    if ticket.status == SupportTicketStatus.closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket fermé.")
    body = _sanitize_text(payload.message)
    if not _message_allowed(body, payload.attachmentUrl):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message or attachment required.")
    row = SupportTicketMessage(
        ticket_id=ticket.id,
        author_role="user",
        author_user_id=current_user.id,
        body=body,
        attachment_url=payload.attachmentUrl,
    )
    db.add(row)
    ticket.message = body
    if ticket.status == SupportTicketStatus.resolved:
        ticket.status = SupportTicketStatus.pending
    notify_admins_support_user_reply(db, ticket, current_user, body)
    ticket = db.scalar(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages))
        .where(SupportTicket.id == ticket.id)
    )
    if ticket:
        notify_employees_ticket_user_reply(db, ticket=ticket, user=current_user, body=body)
    write_log(
        db,
        action="support.user_reply",
        message=f"Réponse client sur ticket #{ticket.id} ({current_user.email})",
        category="admin",
        level="INFO",
        user_id=current_user.id,
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
    return _message_to_read(row)


@router.get("/notifications", response_model=ClientNotificationListResponse)
def list_client_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientNotificationListResponse:
    rows = list(
        db.scalars(
            select(ClientNotification)
            .where(ClientNotification.user_id == current_user.id)
            .order_by(ClientNotification.created_at.desc())
            .limit(50)
        ).all()
    )
    unread = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == current_user.id, ClientNotification.is_read.is_(False))
        )
        or 0
    )
    return ClientNotificationListResponse(
        items=[_client_notif_to_read(r) for r in rows],
        unread_count=unread,
    )


@router.get("/notifications/unread-count")
def client_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    count = int(
        db.scalar(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.user_id == current_user.id, ClientNotification.is_read.is_(False))
        )
        or 0
    )
    return {"count": count}


@router.patch("/notifications/{notif_id}/read", response_model=ClientNotificationRead)
def mark_client_notification_read(
    notif_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientNotificationRead:
    from datetime import datetime, timezone

    row = db.get(ClientNotification, notif_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable.")
    row.is_read = True
    row.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _client_notif_to_read(row)


admin_support_router = APIRouter(prefix="/admin/support", tags=["admin-support"])


@admin_support_router.get("/tickets", response_model=SupportTicketListResponse)
def admin_list_tickets(
    status_filter: str = Query(default="open", alias="status"),
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SupportTicketListResponse:
    stmt = select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(100)
    if status_filter != "all":
        stmt = stmt.where(SupportTicket.status == status_filter)
    rows = list(db.scalars(stmt).all())
    return SupportTicketListResponse(items=[_ticket_to_read(t) for t in rows])


@admin_support_router.get("/tickets/{ticket_id}", response_model=SupportTicketAdminDetailRead)
def admin_get_ticket(
    ticket_id: int,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SupportTicketAdminDetailRead:
    ticket = db.scalar(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages).joinedload(SupportTicketMessage.author))
        .options(joinedload(SupportTicket.user))
        .where(SupportTicket.id == ticket_id)
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    base = _ticket_to_read(ticket)
    user = ticket.user
    return SupportTicketAdminDetailRead(
        **base.model_dump(),
        messages=[_message_to_read(m) for m in ticket.messages],
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
    )


@admin_support_router.post("/tickets/{ticket_id}/reply", response_model=SupportTicketMessageRead)
def admin_reply_ticket(
    ticket_id: int,
    payload: SupportMessageCreate,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SupportTicketMessageRead:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    body = _sanitize_text(payload.message)
    if not _message_allowed(body, payload.attachmentUrl):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message or attachment required.")
    row = SupportTicketMessage(
        ticket_id=ticket.id,
        author_role="admin",
        author_user_id=admin.id,
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
        sender_id=admin.id,
        sender_role="admin",
        priority=ticket.priority or "medium",
        related_ticket_id=ticket.id,
        link=f"/notifications?ticket={ticket.id}",
    )
    ticket = db.scalar(
        select(SupportTicket)
        .options(joinedload(SupportTicket.messages))
        .where(SupportTicket.id == ticket.id)
    )
    if ticket:
        notify_employee_ticket_admin_reply(db, ticket=ticket, admin_id=admin.id, body=body)
    write_log(
        db,
        action="support.admin_reply",
        message=f"Réponse admin sur ticket #{ticket.id}",
        category="admin",
        level="INFO",
        user_id=ticket.user_id,
        actor_user_id=admin.id,
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
    return _message_to_read(row)


@admin_support_router.patch("/tickets/{ticket_id}/status", response_model=SupportTicketRead)
def admin_update_ticket_status(
    ticket_id: int,
    payload: SupportTicketStatusUpdate,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SupportTicketRead:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    ticket.status = payload.status
    db.commit()
    db.refresh(ticket)
    return _ticket_to_read(ticket)


@admin_support_router.patch("/tickets/{ticket_id}/close", response_model=SupportTicketRead)
def admin_close_ticket(
    ticket_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SupportTicketRead:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    ticket.status = SupportTicketStatus.closed
    db.commit()
    db.refresh(ticket)
    return _ticket_to_read(ticket)


@router.patch("/tickets/{ticket_id}/status", response_model=SupportTicketRead)
def update_ticket_status(
    ticket_id: int,
    payload: SupportTicketStatusUpdate,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> SupportTicketRead:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    ticket.status = payload.status
    db.commit()
    db.refresh(ticket)
    return _ticket_to_read(ticket)
