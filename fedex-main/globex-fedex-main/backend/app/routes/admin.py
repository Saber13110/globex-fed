import secrets
import string
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.activity_log import ActivityLog
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole, UserStatus
from app.models.user_session import UserSession
from app.routes.deps import require_role
from app.schemas.admin import (
    ActivityLogListResponse,
    ActivityLogRead,
    AdminDashboardStats,
    AdminInviteUserRequest,
    AdminInviteUserResponse,
    AdminNotificationItem,
    AdminNotificationsResponse,
    AdminUserDetail,
    AdminUserListItem,
    AdminUserUpdate,
)
from app.schemas.user import UserRead, UserSessionRead
from app.schemas.quota import QuotaLimitsRead, QuotaUsageRead, UserQuotaStatus
from app.models.preference_submission import PreferenceSubmission, PreferenceSubmissionStatus
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.schemas.command_center import (
    CommandCenterAiRequest,
    CommandCenterAiResponse,
    CommandCenterPayload,
)
from app.schemas.preference import PreferenceRejectRequest, PreferenceSubmissionRead
from app.schemas.admin_conversations import AdminConversationDetail, AdminConversationsPage
from app.schemas.admin_ai import (
    AiAssistantOverview,
    AiAssistantQueryRequest,
    AiAssistantQueryResponse,
    AdminExportDownloadSpec,
    ExportExecuteRequest,
    ExportExecuteResponse,
)
from app.services.admin_conversations_service import build_conversation_detail, build_conversations_page
from app.services.admin_ai_service import build_ai_assistant_overview
from app.services.admin_copilot_service import run_admin_copilot_analysis, run_admin_copilot_query
from app.services.ai_assistant.response_builder import (
    build_error_fallback_response,
    build_timeout_fallback_response,
    enrich_copilot_response,
)
from app.services.llm.gemini_budget import gemini_request_scope, note_tools

logger = logging.getLogger(__name__)
from app.services.admin_logs_export_service import fetch_activity_logs, generate_activity_logs_pdf
from app.services.command_center_service import build_command_center
from app.services import llm_service
from app.services.activity_log_service import client_ip, write_log
from app.services.preference_profile import profile_from_json
from app.services.preference_service import (
    approve_submission,
    parse_risk_reasons,
    reject_submission,
    validate_admin_active_preferences,
)
from app.services.quota_service import build_quota_status
from app.services.email_service import is_email_configured, send_email
from app.routes import gpt_knowledge

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(gpt_knowledge.router)


class TestEmailRequest(BaseModel):
    to: EmailStr


def _users_by_id(db: Session, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids))).all()
    return {u.id: u for u in rows}


def _log_to_read(row: ActivityLog, users_map: dict[int, User]) -> ActivityLogRead:
    subject = users_map.get(row.user_id) if row.user_id else None
    actor = users_map.get(row.actor_user_id) if row.actor_user_id else None
    return ActivityLogRead(
        id=row.id,
        user_id=row.user_id,
        actor_user_id=row.actor_user_id,
        user_email=subject.email if subject else None,
        user_name=subject.full_name if subject else None,
        actor_email=actor.email if actor else None,
        level=row.level,
        category=row.category,
        action=row.action,
        message=row.message,
        metadata_json=row.metadata_json,
        ip_address=row.ip_address,
        created_at=row.created_at,
    )


@router.get("/dashboard", response_model=AdminDashboardStats)
def dashboard_stats(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminDashboardStats:
    """Métriques agrégées pour le tableau de bord administrateur."""
    settings = get_settings()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def count_users(role: str | None = None, status: str | None = None) -> int:
        stmt = select(func.count()).select_from(User)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if status is not None:
            stmt = stmt.where(User.status == status)
        return int(db.scalar(stmt) or 0)

    return AdminDashboardStats(
        total_users=count_users(),
        total_clients=count_users(UserRole.client.value),
        total_employees=count_users(UserRole.employe.value),
        total_admins=count_users(UserRole.admin.value),
        total_sessions=int(db.scalar(select(func.count()).select_from(ChatSession)) or 0),
        total_messages=int(db.scalar(select(func.count()).select_from(ChatMessage)) or 0),
        total_tracking_requests=int(db.scalar(select(func.count()).select_from(TrackingRequest)) or 0),
        pending_employees=count_users(UserRole.employe.value, UserStatus.pending.value),
        messages_last_7_days=int(
            db.scalar(
                select(func.count()).select_from(ChatMessage).where(ChatMessage.created_at >= since)
            )
            or 0
        ),
        trackings_last_7_days=int(
            db.scalar(
                select(func.count()).select_from(TrackingRequest).where(TrackingRequest.created_at >= since)
            )
            or 0
        ),
        new_users_last_7_days=int(
            db.scalar(select(func.count()).select_from(User).where(User.created_at >= since)) or 0
        ),
        sessions_last_7_days=int(
            db.scalar(
                select(func.count()).select_from(ChatSession).where(ChatSession.created_at >= since)
            )
            or 0
        ),
        logs_last_7_days=int(
            db.scalar(
                select(func.count()).select_from(ActivityLog).where(ActivityLog.created_at >= since)
            )
            or 0
        ),
        total_events=int(db.scalar(select(func.count()).select_from(ActivityLog)) or 0),
        events_today=int(
            db.scalar(
                select(func.count()).select_from(ActivityLog).where(ActivityLog.created_at >= today_start)
            )
            or 0
        ),
        pending_preference_submissions=int(
            db.scalar(
                select(func.count())
                .select_from(PreferenceSubmission)
                .where(PreferenceSubmission.status == PreferenceSubmissionStatus.pending.value)
            )
            or 0
        ),
        email_configured=is_email_configured(),
        fedex_enabled=settings.fedex_enabled,
        llm_enabled=settings.llm_enabled,
    )


@router.get("/notifications", response_model=AdminNotificationsResponse)
def admin_notifications(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=100),
) -> AdminNotificationsResponse:
    """Alertes in-app : employés et préférences IA en attente de validation."""
    items: list[AdminNotificationItem] = []

    pending_employees = list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.employe.value, User.status == UserStatus.pending.value)
            .order_by(User.created_at.desc())
            .limit(limit)
        ).all()
    )
    for user in pending_employees:
        items.append(
            AdminNotificationItem(
                id=f"emp-{user.id}",
                kind="employee_pending",
                reference_id=user.id,
                user_name=user.full_name,
                user_email=user.email,
                created_at=user.created_at,
            )
        )

    pref_rows = list(
        db.scalars(
            select(PreferenceSubmission)
            .where(PreferenceSubmission.status == PreferenceSubmissionStatus.pending.value)
            .order_by(PreferenceSubmission.created_at.desc())
            .limit(limit)
        ).all()
    )
    if pref_rows:
        user_ids = {r.user_id for r in pref_rows}
        users_map = _users_by_id(db, user_ids)
        for row in pref_rows:
            subject = users_map.get(row.user_id)
            items.append(
                AdminNotificationItem(
                    id=f"pref-{row.id}",
                    kind="preference_pending",
                    reference_id=row.id,
                    user_name=subject.full_name if subject else None,
                    user_email=subject.email if subject else None,
                    risk_score=row.risk_score,
                    created_at=row.created_at,
                )
            )

    ticket_rows = list(
        db.scalars(
            select(SupportTicket)
            .where(SupportTicket.status == SupportTicketStatus.open)
            .order_by(SupportTicket.created_at.desc())
            .limit(limit)
        ).all()
    )
    if ticket_rows:
        ticket_user_ids = {t.user_id for t in ticket_rows}
        ticket_users = _users_by_id(db, ticket_user_ids)
        for ticket in ticket_rows:
            subject_user = ticket_users.get(ticket.user_id)
            items.append(
                AdminNotificationItem(
                    id=f"ticket-{ticket.id}",
                    kind="support_ticket",
                    reference_id=ticket.id,
                    user_name=subject_user.full_name if subject_user else None,
                    user_email=subject_user.email if subject_user else None,
                    created_at=ticket.created_at,
                )
            )

    items.sort(key=lambda x: x.created_at, reverse=True)
    items = items[:limit]
    return AdminNotificationsResponse(items=items, total=len(items))


@router.get("/logs", response_model=ActivityLogListResponse)
def list_activity_logs(
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    user_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    level: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ActivityLogListResponse:
    """Journal d'événements (style observateur Windows) — filtrable."""
    if user_id is not None and offset == 0:
        target = db.get(User, user_id)
        write_log(
            db,
            action="admin.logs_view",
            message=f"Consultation journaux utilisateur : {target.email if target else user_id}",
            category="admin",
            level="INFO",
            user_id=user_id,
            actor_user_id=admin.id,
            ip_address=client_ip(request),
            metadata={"filters": {"category": category, "level": level, "q": q}},
            commit=True,
        )

    stmt = select(ActivityLog)
    count_stmt = select(func.count()).select_from(ActivityLog)

    if user_id is not None:
        stmt = stmt.where(or_(ActivityLog.user_id == user_id, ActivityLog.actor_user_id == user_id))
        count_stmt = count_stmt.where(or_(ActivityLog.user_id == user_id, ActivityLog.actor_user_id == user_id))
    if category:
        cat = category.strip().lower()
        stmt = stmt.where(ActivityLog.category == cat)
        count_stmt = count_stmt.where(ActivityLog.category == cat)
    if level:
        lvl = level.strip().upper()
        stmt = stmt.where(ActivityLog.level == lvl)
        count_stmt = count_stmt.where(ActivityLog.level == lvl)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(ActivityLog.message.ilike(pattern), ActivityLog.action.ilike(pattern)))
        count_stmt = count_stmt.where(or_(ActivityLog.message.ilike(pattern), ActivityLog.action.ilike(pattern)))

    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit).offset(offset)).all()
    )
    ids: set[int] = set()
    for row in rows:
        if row.user_id:
            ids.add(row.user_id)
        if row.actor_user_id:
            ids.add(row.actor_user_id)
    users_map = _users_by_id(db, ids)
    return ActivityLogListResponse(
        items=[_log_to_read(row, users_map) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _quota_status_model(db: Session, user: User) -> UserQuotaStatus:
    raw = build_quota_status(db, user)
    return UserQuotaStatus(
        limits=QuotaLimitsRead(**raw["limits"]),
        usage=QuotaUsageRead(**raw["usage"]),
        remaining=QuotaLimitsRead(**raw["remaining"]),
        exempt=raw["exempt"],
    )


def _apply_quota_column(user: User, attr: str, value: int | None) -> bool:
    """value None = pas de changement ; 0 = illimité ; >0 = limite."""
    if value is None:
        return False
    new_val = None if value == 0 else value
    if getattr(user, attr) != new_val:
        setattr(user, attr, new_val)
        return True
    return False


_ONLINE_WINDOW = timedelta(minutes=15)


def _online_cutoff() -> datetime:
    return datetime.now(timezone.utc) - _ONLINE_WINDOW


def _session_stats(db: Session, user_ids: list[int]) -> dict[int, dict]:
    if not user_ids:
        return {}
    cutoff = _online_cutoff()
    rows = db.execute(
        select(
            UserSession.user_id,
            func.max(UserSession.updated_at).label("last_activity_at"),
            func.max(
                case(
                    (and_(UserSession.is_active.is_(True), UserSession.updated_at >= cutoff), 1),
                    else_=0,
                )
            ).label("is_online"),
        )
        .where(UserSession.user_id.in_(user_ids))
        .group_by(UserSession.user_id)
    ).all()
    return {
        row.user_id: {
            "last_activity_at": row.last_activity_at,
            "is_online": bool(row.is_online),
        }
        for row in rows
    }


def _last_locations(db: Session, user_ids: list[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(UserSession.user_id, UserSession.location, UserSession.updated_at)
        .where(UserSession.user_id.in_(user_ids))
        .order_by(UserSession.user_id, UserSession.updated_at.desc())
    ).all()
    out: dict[int, str] = {}
    for row in rows:
        if row.user_id not in out and row.location and row.location != "Unknown":
            out[row.user_id] = row.location
    return out


def _message_counts(db: Session, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(ChatSession.user_id, func.count(ChatMessage.id))
        .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id.in_(user_ids))
        .group_by(ChatSession.user_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def _tracking_counts(db: Session, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(TrackingRequest.user_id, func.count(TrackingRequest.id))
        .where(TrackingRequest.user_id.in_(user_ids))
        .group_by(TrackingRequest.user_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def _build_admin_user_list_item(
    user: User,
    *,
    session_stats: dict[int, dict],
    locations: dict[int, str],
    messages: dict[int, int],
    trackings: dict[int, int],
) -> AdminUserListItem:
    stats = session_stats.get(user.id, {})
    return AdminUserListItem(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        status=user.status,
        organization_id=user.organization_id,
        preferred_language=user.preferred_language,
        created_at=user.created_at,
        last_activity_at=stats.get("last_activity_at"),
        is_online=bool(stats.get("is_online")),
        last_location=locations.get(user.id),
        messages_count=messages.get(user.id, 0),
        trackings_count=trackings.get(user.id, 0),
    )


def _build_admin_user_detail(db: Session, user_id: int) -> AdminUserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    sessions_count = int(
        db.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.user_id == user_id)) or 0
    )
    messages_count = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.user_id == user_id)
        )
        or 0
    )
    trackings_count = int(
        db.scalar(select(func.count()).select_from(TrackingRequest).where(TrackingRequest.user_id == user_id)) or 0
    )
    stats = _session_stats(db, [user_id]).get(user_id, {})
    locations = _last_locations(db, [user_id])
    recent_sessions = list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.updated_at.desc())
            .limit(5)
        ).all()
    )
    return AdminUserDetail(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        status=user.status,
        preferred_language=user.preferred_language,
        response_preferences=user.response_preferences or "",
        organization_id=user.organization_id,
        created_at=user.created_at,
        sessions_count=sessions_count,
        messages_count=messages_count,
        trackings_count=trackings_count,
        last_activity_at=stats.get("last_activity_at"),
        is_online=bool(stats.get("is_online")),
        last_location=locations.get(user_id),
        recent_sessions=[UserSessionRead.model_validate(s) for s in recent_sessions],
        quotas=_quota_status_model(db, user),
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user_detail(
    user_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminUserDetail:
    detail = _build_admin_user_detail(db, user_id)
    write_log(
        db,
        action="admin.user_view",
        message=f"Fiche utilisateur consultée : {detail.email}",
        category="admin",
        level="INFO",
        user_id=user_id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return detail


@router.patch("/users/{user_id}", response_model=AdminUserDetail)
def update_user_admin(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminUserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    changes: list[str] = []
    if payload.full_name is not None and payload.full_name.strip() and payload.full_name.strip() != user.full_name:
        user.full_name = payload.full_name.strip()
        changes.append("nom")
    if payload.role is not None and payload.role in {UserRole.client.value, UserRole.employe.value, UserRole.admin.value}:
        if payload.role != user.role:
            if user.role == UserRole.admin.value and payload.role != UserRole.admin.value:
                admins = int(
                    db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.admin.value)) or 0
                )
                if admins <= 1:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Impossible de retirer le dernier administrateur.",
                    )
            user.role = payload.role
            changes.append("rôle")
    if payload.status is not None and payload.status in {
        UserStatus.pending.value,
        UserStatus.invited.value,
        UserStatus.active.value,
        UserStatus.suspended.value,
    }:
        if payload.status != user.status:
            user.status = payload.status
            changes.append("statut")
    if payload.preferred_language is not None and payload.preferred_language.strip():
        if payload.preferred_language.strip() != user.preferred_language:
            user.preferred_language = payload.preferred_language.strip()[:8]
            changes.append("langue")
    if payload.response_preferences is not None and payload.response_preferences != user.response_preferences:
        user.response_preferences = validate_admin_active_preferences(payload.response_preferences)
        changes.append("instructions IA")
    if _apply_quota_column(user, "quota_messages_per_day", payload.quota_messages_per_day):
        changes.append("quota messages/j")
    if _apply_quota_column(user, "quota_trackings_per_day", payload.quota_trackings_per_day):
        changes.append("quota suivis/j")
    if _apply_quota_column(user, "quota_exports_per_day", payload.quota_exports_per_day):
        changes.append("quota exports/j")

    if changes:
        write_log(
            db,
            action="admin.user_update",
            message=f"Profil modifié par admin ({', '.join(changes)}) : {user.email}",
            category="admin",
            level="INFO",
            user_id=user.id,
            actor_user_id=admin.id,
            ip_address=client_ip(request),
            metadata={"fields": changes},
        )
    db.commit()
    return _build_admin_user_detail(db, user_id)


class AdminSuspendUserRequest(BaseModel):
    reason: str = ""


@router.post("/users/{user_id}/suspend", response_model=dict)
def suspend_user_admin(
    user_id: int,
    request: Request,
    payload: AdminSuspendUserRequest = AdminSuspendUserRequest(),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.security_ids_service import suspend_user

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    if user.role == UserRole.admin.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossible de suspendre un administrateur.",
        )
    reason = payload.reason.strip() or f"Suspension manuelle par administrateur ({admin.email})"
    ok = suspend_user(db, user_id, reason=reason, actor_admin_id=admin.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Compte déjà suspendu ou action impossible.",
        )
    write_log(
        db,
        action="admin.user_suspend",
        message=f"Suspension via admin : {user.email}",
        category="admin",
        level="WARNING",
        user_id=user_id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"reason": reason[:500]},
        commit=True,
    )
    return {"suspended": True, "user_id": user_id}


@router.post("/users/{user_id}/reactivate", response_model=dict)
def reactivate_user_admin(
    user_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.security_ids_service import reactivate_user

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    ok = reactivate_user(db, user_id, actor_admin_id=admin.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Réactivation impossible.",
        )
    write_log(
        db,
        action="admin.user_reactivate",
        message=f"Réactivation via admin : {user.email}",
        category="admin",
        level="INFO",
        user_id=user_id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return {"reactivated": True, "user_id": user_id}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_admin(
    user_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossible de supprimer votre propre compte.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    if user.role == UserRole.admin.value:
        admins = int(
            db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.admin.value)) or 0
        )
        if admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Impossible de supprimer le dernier administrateur.",
            )
    email = user.email
    write_log(
        db,
        action="admin.user_delete",
        message=f"Utilisateur supprimé par admin : {email}",
        category="admin",
        level="WARNING",
        user_id=user.id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"role": user.role, "status": user.status},
    )
    db.delete(user)
    db.commit()


@router.post("/users/invite", response_model=AdminInviteUserResponse)
def invite_user(
    payload: AdminInviteUserRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminInviteUserResponse:
    """Invite un utilisateur — crée le compte et envoie un email d'activation."""
    email = payload.email.lower().strip()
    existing = db.scalar(select(User.id).where(User.email == email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec cet email.")

    role = payload.role.strip().lower()
    if role not in {UserRole.client.value, UserRole.employe.value, UserRole.admin.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rôle invalide.")

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=get_password_hash(secrets.token_urlsafe(24)),
        role=role,
        status=UserStatus.invited.value,
        activation_token=token,
        activation_expires_at=expires,
        preferred_language=payload.preferred_language or "fr",
        organization_id=str(secrets.token_hex(16)),
    )
    db.add(user)
    db.flush()

    settings = get_settings()
    activate_url = f"{settings.frontend_base_url.rstrip('/')}/activate?token={token}"
    email_sent = False
    msg = "Utilisateur invité. Email non envoyé (SMTP non configuré)."

    if is_email_configured():
        try:
            send_email(
                to=email,
                subject="Invitation — Globex FedEx Platform",
                body_text=(
                    f"Bonjour {user.full_name},\n\n"
                    f"Vous avez été invité(e) sur la plateforme Globex FedEx en tant que {role}.\n"
                    f"Activez votre compte : {activate_url}\n\n"
                    "L'équipe Globex FedEx."
                ),
                body_html=(
                    f"<p>Bonjour <strong>{user.full_name}</strong>,</p>"
                    "<p>Vous avez été invité(e) sur la plateforme <strong>Globex FedEx</strong>.</p>"
                    f'<p><a href="{activate_url}" style="display:inline-block;padding:12px 24px;'
                    f'background:linear-gradient(135deg,#6D28FF,#8B5CF6);color:#fff;text-decoration:none;'
                    f'border-radius:10px;font-weight:600;">Activer mon compte</a></p>'
                    f'<p><small>Lien : {activate_url}</small></p>'
                ),
            )
            email_sent = True
            msg = f"Invitation envoyée à {email}."
        except Exception as exc:  # noqa: BLE001
            msg = f"Utilisateur créé. Échec email : {exc}"

    write_log(
        db,
        action="admin.user_invite",
        message=f"Invitation utilisateur : {email} ({role})",
        category="admin",
        level="SUCCESS",
        user_id=user.id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return AdminInviteUserResponse(user=user, email_sent=email_sent, message=msg)


@router.get("/users", response_model=list[AdminUserListItem])
def list_users(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[AdminUserListItem]:
    """Liste tous les utilisateurs avec métadonnées d'activité. Réservé à l'administrateur."""
    users = list(db.scalars(select(User).order_by(User.created_at.desc())).all())
    if not users:
        return []
    user_ids = [u.id for u in users]
    session_stats = _session_stats(db, user_ids)
    locations = _last_locations(db, user_ids)
    messages = _message_counts(db, user_ids)
    trackings = _tracking_counts(db, user_ids)
    return [
        _build_admin_user_list_item(
            user,
            session_stats=session_stats,
            locations=locations,
            messages=messages,
            trackings=trackings,
        )
        for user in users
    ]


@router.post("/test-email")
def test_email(
    payload: TestEmailRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Envoie un email de test. Réservé à l'administrateur (valide la config SMTP)."""
    if not is_email_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service email non configuré (vérifiez les variables SMTP_*).",
        )
    try:
        send_email(
            to=payload.to,
            subject="Test — Globex FedEx Chatbot",
            body_text="Ceci est un email de test envoyé depuis le chatbot Globex FedEx. La configuration SMTP fonctionne.",
            body_html=(
                "<p>Ceci est un <strong>email de test</strong> envoyé depuis le chatbot "
                "Globex&nbsp;FedEx.</p><p>La configuration SMTP fonctionne ✅</p>"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - on remonte un message clair à l'admin
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec de l'envoi SMTP : {exc}",
        ) from exc

    write_log(
        db,
        action="admin.test_email",
        message=f"Email de test envoyé à {payload.to}",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        commit=True,
    )
    return {"sent": True}


@router.get("/employees/pending", response_model=list[UserRead])
def list_pending_employees(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[User]:
    """Liste les demandes d'inscription employé en attente de validation."""
    rows = db.scalars(
        select(User)
        .where(User.role == UserRole.employe.value, User.status == UserStatus.pending.value)
        .order_by(User.created_at.desc())
    ).all()
    return list(rows)


@router.post("/employees/{user_id}/validate", response_model=UserRead)
def validate_employee(
    user_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> User:
    """Valide une demande d'employé : active le compte et envoie un email de confirmation."""
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.employe.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable.")
    if user.status == UserStatus.active.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce compte est déjà actif.")

    if not is_email_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service email non configuré (vérifiez les variables SMTP_*).",
        )

    settings = get_settings()
    login_url = f"{settings.frontend_base_url.rstrip('/')}/employee/login"

    try:
        send_email(
            to=user.email,
            subject="Votre compte employé Globex FedEx a été validé",
            body_text=(
                f"Bonjour {user.full_name},\n\nVotre demande d'inscription employé a été validée "
                "par un administrateur.\n\nVous pouvez dès maintenant vous connecter avec l'email "
                f"et le mot de passe choisis lors de votre inscription :\n{login_url}\n\n"
                "L'équipe Globex FedEx."
            ),
            body_html=(
                f"<p>Bonjour {user.full_name},</p>"
                "<p>Votre demande d'inscription <strong>employé</strong> a été validée par un administrateur.</p>"
                "<p>Vous pouvez dès maintenant vous connecter avec l'email et le mot de passe "
                "choisis lors de votre inscription.</p>"
                f'<p><a href="{login_url}" '
                'style="display:inline-block;padding:12px 20px;background:#4d148c;color:#fff;'
                'text-decoration:none;border-radius:8px;font-weight:600;">Se connecter</a></p>'
                f'<p>Ou copiez ce lien&nbsp;:<br><a href="{login_url}">{login_url}</a></p>'
                "<p>L'équipe Globex&nbsp;FedEx.</p>"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec de l'envoi de l'email : {exc}",
        ) from exc

    user.status = UserStatus.active.value
    user.activation_token = None
    user.activation_expires_at = None
    write_log(
        db,
        action="admin.employee_validate",
        message=f"Compte employé validé : {user.email}",
        category="admin",
        level="SUCCESS",
        user_id=user.id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/employees/{user_id}/reset-password", response_model=UserRead)
def reset_employee_password(
    user_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> User:
    """Génère un mot de passe temporaire et l'envoie par email (récupération de compte)."""
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.employe.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable.")

    if not is_email_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service email non configuré (vérifiez les variables SMTP_*).",
        )

    alphabet = string.ascii_letters + string.digits
    temp_password = "".join(secrets.choice(alphabet) for _ in range(12))
    user.password_hash = get_password_hash(temp_password)
    user.status = UserStatus.active.value
    user.activation_token = None
    user.activation_expires_at = None

    settings = get_settings()
    login_url = f"{settings.frontend_base_url.rstrip('/')}/employee/login"

    try:
        send_email(
            to=user.email,
            subject="Réinitialisation de votre mot de passe employé Globex FedEx",
            body_text=(
                f"Bonjour {user.full_name},\n\nUn administrateur a réinitialisé votre mot de passe.\n\n"
                f"Mot de passe temporaire : {temp_password}\n\n"
                f"Connectez-vous ici : {login_url}\n\n"
                "Pensez à le modifier après connexion.\n\nL'équipe Globex FedEx."
            ),
            body_html=(
                f"<p>Bonjour {user.full_name},</p>"
                "<p>Un administrateur a réinitialisé votre mot de passe.</p>"
                f"<p><strong>Mot de passe temporaire :</strong> {temp_password}</p>"
                f'<p><a href="{login_url}">Se connecter</a></p>'
                "<p>Pensez à le modifier après connexion.</p>"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec de l'envoi de l'email : {exc}",
        ) from exc

    write_log(
        db,
        action="admin.employee_reset_password",
        message=f"Mot de passe réinitialisé pour {user.email}",
        category="admin",
        level="WARNING",
        user_id=user.id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/employees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def reject_employee(
    user_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    """Refuse (supprime) une demande d'employé non encore activée."""
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.employe.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable.")
    if user.status == UserStatus.active.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce compte est déjà actif et ne peut pas être refusé ici.",
        )
    email = user.email
    write_log(
        db,
        action="admin.employee_reject",
        message=f"Demande employé refusée : {email}",
        category="admin",
        level="WARNING",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"rejected_user_id": user_id},
    )
    db.delete(user)
    db.commit()


def _submission_to_read(row: PreferenceSubmission, users_map: dict[int, User]) -> PreferenceSubmissionRead:
    subject = users_map.get(row.user_id)
    structured = profile_from_json(row.structured_json)
    return PreferenceSubmissionRead(
        id=row.id,
        user_id=row.user_id,
        user_email=subject.email if subject else None,
        user_name=subject.full_name if subject else None,
        proposed_text=row.proposed_text,
        structured=structured,
        status=row.status,
        risk_score=row.risk_score,
        risk_reasons=parse_risk_reasons(row.risk_reasons),
        rejection_note=row.rejection_note,
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


@router.get("/preferences/pending", response_model=list[PreferenceSubmissionRead])
def list_pending_preferences(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PreferenceSubmissionRead]:
    rows = list(
        db.scalars(
            select(PreferenceSubmission)
            .where(PreferenceSubmission.status == PreferenceSubmissionStatus.pending.value)
            .order_by(PreferenceSubmission.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    ids = {r.user_id for r in rows}
    users_map = _users_by_id(db, ids)
    return [_submission_to_read(r, users_map) for r in rows]


@router.post("/preferences/{submission_id}/approve", response_model=PreferenceSubmissionRead)
def approve_preference_submission(
    submission_id: int,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> PreferenceSubmissionRead:
    row = approve_submission(db, submission_id, admin)
    write_log(
        db,
        action="admin.preference_approved",
        message=f"Préférences approuvées pour user_id={row.user_id}",
        category="admin",
        level="SUCCESS",
        user_id=row.user_id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"submission_id": submission_id},
        commit=False,
    )
    db.commit()
    db.refresh(row)
    users_map = _users_by_id(db, {row.user_id})
    return _submission_to_read(row, users_map)


@router.post("/preferences/{submission_id}/reject", response_model=PreferenceSubmissionRead)
def reject_preference_submission(
    submission_id: int,
    payload: PreferenceRejectRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> PreferenceSubmissionRead:
    row = reject_submission(db, submission_id, admin, payload.note)
    write_log(
        db,
        action="admin.preference_rejected",
        message=f"Préférences refusées pour user_id={row.user_id}",
        category="admin",
        level="WARNING",
        user_id=row.user_id,
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"submission_id": submission_id},
        commit=False,
    )
    db.commit()
    db.refresh(row)
    users_map = _users_by_id(db, {row.user_id})
    return _submission_to_read(row, users_map)


@router.get("/ai-assistant/overview", response_model=AiAssistantOverview)
def get_ai_assistant_overview(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AiAssistantOverview:
    """Vue d'ensemble AI Assistant — KPIs, insights, conversations, statuts."""
    return build_ai_assistant_overview(db)


@router.post("/ai-assistant/query", response_model=AiAssistantQueryResponse)
def ai_assistant_query(
    payload: AiAssistantQueryRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AiAssistantQueryResponse:
    """Requête copilot admin — exécution réelle via runtime Agent Missions."""
    logger.info("[AI] request received — %.120s", payload.message)
    result: dict
    try:
        hist = [
            {"role": m.role, "content": m.content}
            for m in (payload.conversation_history or [])
        ]
        settings = get_settings()
        max_calls = (
            settings.gemini_max_calls_agent_mode
            if payload.agent_mode
            else settings.gemini_max_calls_per_request
        )
        req_id = request.headers.get("X-Request-ID") or request.headers.get("X-Request-Id")

        with gemini_request_scope(request_id=req_id, max_calls=max_calls):
            if payload.agent_mode:
                result = run_admin_copilot_query(
                    db,
                    admin,
                    payload.message,
                    quick_action=payload.quick_action,
                    conversation_history=hist,
                    copilot_state=(
                        payload.copilot_state.model_dump()
                        if hasattr(payload.copilot_state, "model_dump")
                        else payload.copilot_state
                    ),
                    image_base64=payload.image_base64,
                    image_mime_type=payload.image_mime_type,
                    attached_document_name=payload.attached_document_name,
                )
            else:
                result = run_admin_copilot_analysis(
                    db,
                    admin,
                    payload.message,
                    quick_action=payload.quick_action,
                    conversation_history=hist,
                    copilot_state=(
                        payload.copilot_state.model_dump()
                        if hasattr(payload.copilot_state, "model_dump")
                        else payload.copilot_state
                    ),
                    image_base64=payload.image_base64,
                    image_mime_type=payload.image_mime_type,
                    attached_document_name=payload.attached_document_name,
                )
            note_tools(result.get("tools_used") or [])
    except Exception as exc:
        logger.exception("[AI] error — pipeline exception")
        result = build_error_fallback_response(str(exc))

    if result.get("mode") == "timeout_fallback" or result.get("error") == "TIMEOUT":
        result = build_timeout_fallback_response(
            intent=result.get("intent") or "timeout",
            tools_used=result.get("tools_used") or [],
        )

    enriched = enrich_copilot_response(result)
    logger.info(
        "[AI] response sent — mode=%s tools=%s",
        enriched.get("mode"),
        enriched.get("tools_used"),
    )

    write_log(
        db,
        action="admin.copilot_query",
        message=f"Copilot — {payload.message[:120]}",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={
            "agent_type": enriched.get("agent_type"),
            "mission_id": enriched.get("mission_id"),
            "action_executed": enriched.get("action_executed"),
            "needs_approval": enriched.get("needs_approval"),
            "mode": enriched.get("mode"),
            "tools_used": enriched.get("tools_used"),
        },
        commit=True,
    )
    return AiAssistantQueryResponse(**enriched)


@router.post("/ai-assistant/export/execute", response_model=ExportExecuteResponse)
def execute_admin_export(
    payload: ExportExecuteRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ExportExecuteResponse:
    """Exécute un export confirmé par l'administrateur."""
    from app.services.ai_assistant.export_workflow_service import execute_export

    action = payload.suggested_action or {}
    if action.get("type") != "export":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action export invalide.",
        )

    result = execute_export(db, admin, action)
    if not result.get("success"):
        return ExportExecuteResponse(
            success=False,
            error=result.get("error"),
            export_status="error",
            reply=result.get("error"),
        )

    records = result.get("records", 0)
    fname = result.get("file_name", "export.pdf")
    reply = (
        f"Export terminé — **{records:,}** enregistrements.\n"
        f"Fichier : `{fname}`\n\n"
        f"Cliquez sur **Télécharger** pour récupérer le fichier."
    )

    write_log(
        db,
        action="admin.export_execute",
        message=f"Export {action.get('module')} {action.get('format')} — {records} records",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"module": action.get("module"), "format": action.get("format"), "records": records},
        commit=True,
    )

    spec = result.get("export_download")
    return ExportExecuteResponse(
        success=True,
        file_name=fname,
        download_url=result.get("download_url"),
        records=records,
        export_download=AdminExportDownloadSpec(**spec) if spec else None,
        export_status="completed",
        reply=reply,
    )


@router.get("/ai-assistant/health")
def ai_assistant_health(
    _: User = Depends(require_role("admin")),
) -> dict:
    """Santé du moteur IA admin — provider, latence, outils, taux succès."""
    from app.services.ai_assistant.health_metrics import get_health_snapshot

    return get_health_snapshot()


@router.get("/ai-assistant/export/activity-logs.pdf")
def export_admin_activity_logs_pdf(
    request: Request,
    hours: int = Query(2, ge=1, le=168),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Téléchargement PDF des journaux d'activité (déclenché par le mode Agent admin)."""
    from io import BytesIO

    logs = fetch_activity_logs(db, hours=hours, limit=500)
    try:
        pdf_bytes, filename = generate_activity_logs_pdf(logs, hours=hours)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Export PDF indisponible : {exc}",
        ) from exc

    write_log(
        db,
        action="admin.export_activity_logs_pdf",
        message=f"Export PDF logs {hours}h — {len(logs)} entrées",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"hours": hours, "entries": len(logs)},
        commit=True,
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ai-assistant/export/tracking-status.pdf")
def export_admin_tracking_status_pdf(
    request: Request,
    numbers: str = Query(..., min_length=10, max_length=500),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Téléchargement PDF des statuts FedEx (déclenché par le copilot admin)."""
    from io import BytesIO

    from app.services import fedex_service
    from app.services.shipment_pdf_service import generate_multi_shipment_history_pdf

    raw = [n.strip() for n in numbers.split(",") if n.strip()]
    tracking_numbers = raw[:10]
    if not tracking_numbers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Numéros de suivi requis.")

    shipments: list[dict] = []
    for tn in tracking_numbers:
        try:
            shipments.append(fedex_service.get_shipment(tn))
        except fedex_service.TrackingLookupError:
            continue

    if not shipments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucun colis trouvé pour ces numéros de suivi.",
        )

    try:
        pdf_bytes = generate_multi_shipment_history_pdf(shipments)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Export PDF indisponible : {exc}",
        ) from exc

    suffix = f"{len(shipments)}-colis" if len(shipments) != 1 else shipments[0].get("tracking_number", "export")
    filename = f"tracking-status-{suffix}.pdf"

    write_log(
        db,
        action="admin.export_tracking_status_pdf",
        message=f"Export PDF tracking — {len(shipments)} colis",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"tracking_numbers": [s.get("tracking_number") for s in shipments]},
        commit=True,
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_CONTEXT_EXPORT_PRESETS: dict[str, str] = {
    "admin_notifications": "notifications",
    "admin_users": "users",
    "admin_tickets": "tickets",
    "admin_conversations": "conversations",
    "admin_tracking": "tracking",
    "admin_generic": "generic",
}


@router.get("/ai-assistant/export/context.pdf")
def export_admin_context_pdf(
    request: Request,
    preset: str = Query(..., min_length=3, max_length=64),
    limit: int = Query(10, ge=1, le=50),
    module: str | None = Query(None, max_length=32),
    hours: int = Query(24, ge=1, le=168),
    export_token: str | None = Query(None, min_length=8, max_length=64),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Export PDF contextuel — utilise le cache session si export_token fourni."""
    from io import BytesIO

    from app.services.ai_assistant.export_dataset_cache import get_export_dataset
    from app.services.ai_assistant.export_normalize import ExportDataError
    from app.services.ai_assistant.export_pipeline import generate_pdf_from_cache
    from app.services.copilot_export_service import build_context_export_pdf

    generated_by = admin.full_name or admin.email or "Administrateur Globex"

    if export_token:
        cached = get_export_dataset(export_token, admin_id=admin.id)
        if not cached:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export expiré ou introuvable — regénérez l'export depuis le copilot.",
            )
        try:
            pdf_bytes, filename = generate_pdf_from_cache(cached, generated_by=generated_by)
            mod = cached.get("module", "generic")
            records = len(cached.get("items") or [])
        except ExportDataError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    else:
        mod = _CONTEXT_EXPORT_PRESETS.get(preset) or module or "generic"
        if mod == "generic" and module:
            mod = module
        try:
            pdf_bytes, filename = build_context_export_pdf(
                db, admin, module=mod, limit=limit, hours=hours,
            )
            records = limit
        except ExportDataError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Export PDF indisponible : {exc}",
            ) from exc

    write_log(
        db,
        action="admin.export_context_pdf",
        message=f"Export PDF {mod} — {records} éléments",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"preset": preset, "module": mod, "limit": records, "export_token": export_token[:8] if export_token else None},
        commit=True,
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ai-assistant/export/context.xlsx")
def export_admin_context_xlsx(
    request: Request,
    preset: str = Query(..., min_length=3, max_length=64),
    limit: int = Query(10, ge=1, le=50),
    export_token: str | None = Query(None, min_length=8, max_length=64),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Export Excel contextuel — utilise le cache session si export_token fourni."""
    from io import BytesIO

    from app.services.ai_assistant.export_dataset_cache import get_export_dataset
    from app.services.ai_assistant.export_normalize import ExportDataError
    from app.services.ai_assistant.export_pipeline import generate_xlsx_from_cache

    if not export_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="export_token requis — regénérez l'export depuis le copilot.",
        )
    cached = get_export_dataset(export_token, admin_id=admin.id)
    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export expiré ou introuvable — regénérez l'export depuis le copilot.",
        )
    try:
        xlsx_bytes, filename = generate_xlsx_from_cache(cached)
        mod = cached.get("module", "generic")
        records = len(cached.get("items") or [])
    except ExportDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    write_log(
        db,
        action="admin.export_context_xlsx",
        message=f"Export XLSX {mod} — {records} éléments",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"preset": preset, "module": mod, "limit": records, "export_token": export_token[:8]},
        commit=True,
    )
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ai-assistant/export/activity-logs.xlsx")
def export_admin_activity_logs_excel(
    request: Request,
    hours: int = Query(24, ge=1, le=168),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Téléchargement Excel des journaux d'activité (colonnes Date, Titre, Type de log)."""
    from io import BytesIO

    from app.services.admin_logs_export_service import generate_activity_logs_excel

    logs = fetch_activity_logs(db, hours=hours, limit=500)
    try:
        excel_bytes, filename = generate_activity_logs_excel(logs, hours=hours)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Export Excel indisponible : {exc}",
        ) from exc

    write_log(
        db,
        action="admin.export_activity_logs_excel",
        message=f"Export Excel logs {hours}h — {len(logs)} entrées",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"hours": hours, "entries": len(logs)},
        commit=True,
    )
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ai-assistant/export/activity-logs.csv")
def export_admin_activity_logs_csv(
    request: Request,
    hours: int = Query(24, ge=1, le=168),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Téléchargement CSV des journaux d'activité."""
    from io import BytesIO

    from app.services.ai_assistant.export_workflow_service import generate_logs_csv

    csv_bytes, filename = generate_logs_csv(db, hours=hours)
    write_log(
        db,
        action="admin.export_activity_logs_csv",
        message=f"Export CSV logs {hours}h",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"hours": hours},
        commit=True,
    )
    return StreamingResponse(
        BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ai-assistant/export/platform-report.pdf")
def export_admin_platform_report_pdf(
    request: Request,
    hours: int = Query(24, ge=1, le=720),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Rapport plateforme IA — Executive Summary + KPI."""
    from io import BytesIO

    from app.services.platform_report_service import generate_platform_report_pdf

    try:
        pdf_bytes, filename = generate_platform_report_pdf(db, admin, hours=hours)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Rapport indisponible : {exc}",
        ) from exc

    write_log(
        db,
        action="admin.export_platform_report",
        message=f"Rapport plateforme {hours}h",
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=client_ip(request),
        metadata={"hours": hours},
        commit=True,
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/command-center", response_model=CommandCenterPayload)
def get_command_center(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> CommandCenterPayload:
    """Tableau de bord Super Admin — métriques temps réel."""
    return build_command_center(db)


@router.get("/conversations", response_model=AdminConversationsPage)
def admin_list_conversations(
    tab: str = Query("all"),
    search: str = Query(""),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminConversationsPage:
    """Liste des conversations IA avec KPIs pour le centre admin."""
    return build_conversations_page(db, tab=tab, search=search)


@router.get("/conversations/{session_id}", response_model=AdminConversationDetail)
def admin_conversation_detail(
    session_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminConversationDetail:
    """Détail d'une conversation (messages, analytics, tags)."""
    detail = build_conversation_detail(db, session_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    return detail


@router.post("/command-center/ai", response_model=CommandCenterAiResponse)
def command_center_ai(
    payload: CommandCenterAiRequest,
    request: Request,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> CommandCenterAiResponse:
    """Requête IA admin (analyses, rapports, activité)."""
    stats = build_command_center(db)
    context = (
        f"Contexte Globex Super Admin: "
        f"utilisateurs actifs={stats.hero_stats[2].value}, "
        f"expéditions aujourd'hui={stats.hero_stats[0].value}, "
        f"incidents ouverts={stats.open_incidents}, "
        f"requêtes FedEx aujourd'hui={stats.fedex_metrics.requests_today}."
    )
    quick = (payload.quick_action or "").strip().lower()
    message = payload.message.strip()
    if quick == "delays":
        message = "Analyse les retards d'expédition probables et résume les actions recommandées."
    elif quick == "exceptions":
        message = "Liste les principales exceptions et incidents du jour."
    elif quick == "report":
        message = "Génère un résumé de performance opérationnelle pour l'administrateur."
    elif quick == "activity":
        message = "Résume l'activité utilisateur récente sur la plateforme."
    elif quick == "countries":
        message = "Compare les performances de livraison par pays et région."
    elif quick == "predict":
        message = "Prédit les retards de livraison probables pour demain et recommande des actions."

    try:
        from app.services.gpt.orchestrator import SLUG_ADMIN, run_gpt_turn

        turn = run_gpt_turn(
            db,
            gpt_slug=SLUG_ADMIN,
            user_id=admin.id,
            message=message,
            ui_language=admin.preferred_language or "fr",
            profile_language=admin.preferred_language,
            operational_context=context,
        )
        reply, intent = turn.reply, turn.intent
    except Exception:
        result = llm_service.generate_response(
            f"{context}\n\nQuestion admin: {message}",
            ui_language=admin.preferred_language or "fr",
        )
        reply, intent = result.reply, result.intent
        write_log(
            db,
            action="admin.command_center_ai",
            message=f"Requête IA admin: {message[:120]}",
            category="admin",
            level="INFO",
            actor_user_id=admin.id,
            ip_address=client_ip(request),
            commit=True,
        )
        return CommandCenterAiResponse(reply=reply, intent=intent)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"IA indisponible : {exc}",
        ) from exc
