"""Façade métier gestion utilisateurs admin — logique extraite de admin.py."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models.activity_log import ActivityLog
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole, UserStatus
from app.models.user_session import UserSession
from app.schemas.admin import ActivityLogListResponse, ActivityLogRead, AdminUserDetail, AdminUserListItem
from app.schemas.quota import QuotaLimitsRead, QuotaUsageRead, UserQuotaStatus
from app.schemas.user import UserSessionRead
from app.services.activity_log_service import write_log
from app.services.email_service import is_email_configured, send_email
from app.services.quota_service import build_quota_status

from app.services.admin_client.users.users_types import UsersToolError

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


def _build_list_item(
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


def _quota_status_model(db: Session, user: User) -> UserQuotaStatus:
    raw = build_quota_status(db, user)
    return UserQuotaStatus(
        limits=QuotaLimitsRead(**raw["limits"]),
        usage=QuotaUsageRead(**raw["usage"]),
        remaining=QuotaLimitsRead(**raw["remaining"]),
        exempt=raw["exempt"],
    )


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


def _normalize_role_filter(role: str | None) -> str | None:
    r = (role or "").strip().lower()
    if not r:
        return None
    if r in {UserRole.client.value, UserRole.employe.value, UserRole.admin.value}:
        return r
    if r in {"employee", "employees", "employe", "employés", "employes"}:
        return UserRole.employe.value
    if r in {"admin", "admins", "administrateur", "administrateurs"}:
        return UserRole.admin.value
    if r in {"client", "clients"}:
        return UserRole.client.value
    return None


def _normalize_status_filter(status: str | None) -> str | None:
    s = (status or "").strip().lower()
    if not s:
        return None
    if s in {UserStatus.active.value, UserStatus.suspended.value, UserStatus.pending.value, UserStatus.invited.value}:
        return s
    if s in {"actif", "actifs", "active"}:
        return UserStatus.active.value
    if s in {"suspendu", "suspendus", "suspendue", "suspendues", "suspended"}:
        return UserStatus.suspended.value
    if s in {"pending", "en attente"}:
        return UserStatus.pending.value
    if s in {"invited", "invité", "invités"}:
        return UserStatus.invited.value
    return None


def list_users_filtered(
    db: Session,
    *,
    role: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 15,
    sort_by: str | None = None,
) -> list[AdminUserListItem]:
    limit = min(max(int(limit or 15), 1), 50)
    role_filter = _normalize_role_filter(role)
    status_filter = _normalize_status_filter(status)
    search = (q or "").strip()
    sort = (sort_by or "").strip().lower() or None

    stmt = select(User).order_by(User.created_at.desc())
    if role_filter:
        stmt = stmt.where(User.role == role_filter)
    if status_filter:
        stmt = stmt.where(User.status == status_filter)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )

    fetch_limit = limit * 4 if sort in {"last_activity", "online"} else limit
    users = list(db.scalars(stmt.limit(fetch_limit)).all())
    if not users:
        return []
    user_ids = [u.id for u in users]
    session_stats = _session_stats(db, user_ids)
    locations = _last_locations(db, user_ids)
    messages = _message_counts(db, user_ids)
    trackings = _tracking_counts(db, user_ids)
    items = [
        _build_list_item(
            user,
            session_stats=session_stats,
            locations=locations,
            messages=messages,
            trackings=trackings,
        )
        for user in users
    ]
    if sort == "last_activity":
        items.sort(
            key=lambda u: u.last_activity_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
    elif sort == "online":
        items.sort(
            key=lambda u: (
                not u.is_online,
                -(u.last_activity_at.timestamp() if u.last_activity_at else 0),
            ),
        )
    return items[:limit]


def list_users_ever_suspended(
    db: Session,
    *,
    role: str | None = None,
    q: str | None = None,
    limit: int = 15,
) -> list[AdminUserListItem]:
    """Utilisateurs ayant été suspendus au moins une fois (journal ActivityLog)."""
    limit = min(max(int(limit or 15), 1), 50)
    role_filter = _normalize_role_filter(role)
    search = (q or "").strip()

    suspend_subq = (
        select(
            ActivityLog.user_id.label("uid"),
            func.max(ActivityLog.created_at).label("last_suspend_at"),
        )
        .where(ActivityLog.action == "admin.user_suspend")
        .where(ActivityLog.user_id.isnot(None))
        .group_by(ActivityLog.user_id)
        .subquery()
    )
    stmt = (
        select(User)
        .join(suspend_subq, User.id == suspend_subq.c.uid)
        .order_by(suspend_subq.c.last_suspend_at.desc())
    )
    if role_filter:
        stmt = stmt.where(User.role == role_filter)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )

    users = list(db.scalars(stmt.limit(limit)).all())
    if not users:
        return []
    user_ids = [u.id for u in users]
    session_stats = _session_stats(db, user_ids)
    locations = _last_locations(db, user_ids)
    messages = _message_counts(db, user_ids)
    trackings = _tracking_counts(db, user_ids)
    return [
        _build_list_item(
            user,
            session_stats=session_stats,
            locations=locations,
            messages=messages,
            trackings=trackings,
        )
        for user in users
    ]


def get_user_detail(db: Session, user_id: int) -> AdminUserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise UsersToolError("user_not_found")
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


def get_user_permissions(db: Session, user_id: int) -> dict[str, Any]:
    detail = get_user_detail(db, user_id)
    quotas = detail.quotas
    return {
        "user_id": detail.id,
        "email": detail.email,
        "full_name": detail.full_name,
        "role": detail.role,
        "status": detail.status,
        "organization_id": detail.organization_id,
        "response_preferences": detail.response_preferences,
        "quotas": quotas.model_dump() if quotas else None,
    }


def get_user_logs(db: Session, user_id: int, *, limit: int = 25) -> ActivityLogListResponse:
    if db.get(User, user_id) is None:
        raise UsersToolError("user_not_found")
    limit = min(max(int(limit or 25), 1), 100)
    stmt = select(ActivityLog).where(
        or_(ActivityLog.user_id == user_id, ActivityLog.actor_user_id == user_id)
    )
    count_stmt = select(func.count()).select_from(ActivityLog).where(
        or_(ActivityLog.user_id == user_id, ActivityLog.actor_user_id == user_id)
    )
    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit)
        ).all()
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
        offset=0,
    )


def search_users_by_query(db: Session, q: str, *, limit: int = 10) -> list[User]:
    search = (q or "").strip()
    if not search:
        return []
    pattern = f"%{search}%"
    return list(
        db.scalars(
            select(User)
            .where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
            .order_by(User.created_at.desc())
            .limit(min(max(limit, 1), 20))
        ).all()
    )


def suspend_user_account(
    db: Session,
    user_id: int,
    admin_id: int,
    *,
    reason: str = "",
    ip_address: str = "",
) -> dict[str, Any]:
    from app.services.security_ids_service import suspend_user

    user = db.get(User, user_id)
    if user is None:
        raise UsersToolError("user_not_found")
    if user.role == UserRole.admin.value:
        raise UsersToolError("cannot_suspend_admin")
    reason_text = reason.strip() or f"Suspension manuelle par administrateur (id={admin_id})"
    ok = suspend_user(db, user_id, reason=reason_text, actor_admin_id=admin_id)
    if not ok:
        raise UsersToolError("already_suspended")
    write_log(
        db,
        action="admin.user_suspend",
        message=f"Suspension via agent admin : {user.email}",
        category="admin",
        level="WARNING",
        user_id=user_id,
        actor_user_id=admin_id,
        ip_address=ip_address or None,
        metadata={"reason": reason_text[:500]},
        commit=True,
    )
    return {"suspended": True, "user_id": user_id, "email": user.email}


def reactivate_user_account(
    db: Session,
    user_id: int,
    admin_id: int,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    from app.services.security_ids_service import reactivate_user

    user = db.get(User, user_id)
    if user is None:
        raise UsersToolError("user_not_found")
    ok = reactivate_user(db, user_id, actor_admin_id=admin_id)
    if not ok:
        raise UsersToolError("reactivate_failed")
    write_log(
        db,
        action="admin.user_reactivate",
        message=f"Réactivation via agent admin : {user.email}",
        category="admin",
        level="INFO",
        user_id=user_id,
        actor_user_id=admin_id,
        ip_address=ip_address or None,
        commit=True,
    )
    return {"reactivated": True, "user_id": user_id, "email": user.email}


def delete_user_account(
    db: Session,
    user_id: int,
    admin_id: int,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    if user_id == admin_id:
        raise UsersToolError("cannot_delete_self")
    user = db.get(User, user_id)
    if user is None:
        raise UsersToolError("user_not_found")
    if user.role == UserRole.admin.value:
        admins = int(
            db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.admin.value)) or 0
        )
        if admins <= 1:
            raise UsersToolError("cannot_delete_last_admin")
    email = user.email
    write_log(
        db,
        action="admin.user_delete",
        message=f"Utilisateur supprimé par agent admin : {email}",
        category="admin",
        level="WARNING",
        user_id=user.id,
        actor_user_id=admin_id,
        ip_address=ip_address or None,
        metadata={"role": user.role, "status": user.status},
    )
    db.delete(user)
    db.commit()
    return {"deleted": True, "user_id": user_id, "email": email}


def update_user_name(
    db: Session,
    user_id: int,
    admin_id: int,
    new_name: str,
    *,
    ip_address: str = "",
) -> AdminUserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise UsersToolError("user_not_found")
    name = (new_name or "").strip()
    if not name:
        raise UsersToolError("invalid_name")
    if name != user.full_name:
        user.full_name = name
        write_log(
            db,
            action="admin.user_update",
            message=f"Nom mis à jour via agent admin : {user.email} → {name}",
            category="admin",
            level="INFO",
            user_id=user_id,
            actor_user_id=admin_id,
            ip_address=ip_address or None,
            metadata={"full_name": name},
            commit=True,
        )
        db.commit()
    return get_user_detail(db, user_id)


def _login_path_for_role(role: str) -> str:
    if role == UserRole.employe.value:
        return "/employee/login"
    if role == UserRole.admin.value:
        return "/admin/login"
    return "/login"


def _role_label_fr(role: str) -> str:
    return {
        UserRole.client.value: "client",
        UserRole.employe.value: "employé",
        UserRole.admin.value: "administrateur",
    }.get(role, role)


def reset_user_password(
    db: Session,
    user_id: int,
    admin_id: int,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise UsersToolError("user_not_found")
    if not is_email_configured():
        raise UsersToolError("smtp_not_configured")

    alphabet = string.ascii_letters + string.digits
    temp_password = "".join(secrets.choice(alphabet) for _ in range(12))
    user.password_hash = get_password_hash(temp_password)
    user.status = UserStatus.active.value
    user.activation_token = None
    user.activation_expires_at = None

    settings = get_settings()
    login_url = f"{settings.frontend_base_url.rstrip('/')}{_login_path_for_role(user.role)}"
    role_label = _role_label_fr(user.role)

    try:
        send_email(
            to=user.email,
            subject=f"Réinitialisation de votre mot de passe Globex FedEx ({role_label})",
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
        raise UsersToolError(f"email_send_failed:{exc}") from exc

    write_log(
        db,
        action="admin.user_reset_password",
        message=f"Mot de passe réinitialisé pour {user.email}",
        category="admin",
        level="WARNING",
        user_id=user.id,
        actor_user_id=admin_id,
        ip_address=ip_address or None,
    )
    db.commit()
    return {"reset": True, "user_id": user_id, "email": user.email}
